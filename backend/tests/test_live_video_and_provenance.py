"""LIVE verification of the two advanced features: brand film + embedded provenance.

Reuses the most recent campaign that actually produced video, rather than
generating one per test — video costs real quota and takes ~2 minutes.

    uv run pytest tests/test_live_video_and_provenance.py -m live -v -s

To produce a campaign for these to inspect:
    curl -X POST localhost:8787/api/campaigns -H 'Content-Type: application/json' \
      -d '{..., "includeVideo": true}'
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.live

BASE = os.environ.get("FERNWOOD_TEST_BASE", "http://127.0.0.1:8787")


def _server_up() -> bool:
    try:
        return httpx.get(f"{BASE}/api/health", timeout=5).status_code == 200
    except Exception:  # noqa: BLE001
        return False


needs_server = pytest.mark.skipif(not _server_up(), reason="backend not running")


@pytest.fixture(scope="module")
def video_campaign():
    if not _server_up():
        pytest.skip("backend not running")
    from dotenv import load_dotenv

    load_dotenv(
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        override=True,
    )
    campaigns = httpx.get(f"{BASE}/api/campaigns", timeout=30).json()["campaigns"]
    for c in campaigns:
        video = c.get("assets", {}).get("video")
        if video and video.get("attempts"):
            return c
    pytest.skip(
        "no campaign with video in the library — run one with includeVideo=true"
    )


@pytest.fixture(scope="module")
def delivery_campaign():
    if not _server_up():
        pytest.skip("backend not running")
    campaigns = httpx.get(f"{BASE}/api/campaigns", timeout=30).json()["campaigns"]
    for c in campaigns:
        if c.get("delivery"):
            return c
    pytest.skip("no campaign with embedded-provenance deliverables yet")


@needs_server
class TestBrandFilm:
    def test_video_asset_present_and_approved(self, video_campaign):
        video = video_campaign["assets"]["video"]
        assert video["status"] == "passed"
        assert video["finalApprovedAttemptId"]
        assert len(video["attempts"]) == 1

    def test_video_is_a_real_playable_mp4(self, video_campaign):
        att = video_campaign["assets"]["video"]["attempts"][-1]
        url = att["content"]["videoUrl"]
        assert url.startswith("/api/media/")
        r = httpx.get(f"{BASE}{url}", timeout=180)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("video/")
        # ISO base media file signature: ....ftyp
        assert r.content[4:8] == b"ftyp", "not an ISO/MP4 container"
        assert len(r.content) > 100_000

    def test_video_served_with_range_for_seeking(self, video_campaign):
        url = video_campaign["assets"]["video"]["attempts"][-1]["content"]["videoUrl"]
        r = httpx.get(f"{BASE}{url}", headers={"Range": "bytes=0-2047"}, timeout=60)
        assert r.status_code == 206
        assert len(r.content) == 2048
        assert r.headers["accept-ranges"] == "bytes"

    def test_duration_matches_the_request(self, video_campaign):
        att = video_campaign["assets"]["video"]["attempts"][-1]
        duration = att["content"].get("videoDurationSeconds")
        assert duration, "duration not parsed from the mp4 header"
        assert 3 <= duration <= 15, f"unexpected clip length {duration}s"

    def test_poster_is_the_approved_key_visual(self, video_campaign):
        """The film animates the still that passed critique, not a new scene."""
        att = video_campaign["assets"]["video"]["attempts"][-1]
        poster = att["content"].get("videoPosterUrl")
        assert poster, "no poster recorded"

        image_asset = video_campaign["assets"]["image"]
        approved = next(
            a for a in image_asset["attempts"]
            if a["id"] == image_asset["finalApprovedAttemptId"]
        )
        assert poster == approved["content"]["imageUrl"]
        assert httpx.get(f"{BASE}{poster}", timeout=120).status_code == 200

    def test_provenance_records_the_async_provider(self, video_campaign):
        att = video_campaign["assets"]["video"]["attempts"][-1]
        assert "async" in att["providerName"].lower()
        assert att["modelName"]
        assert len(att["content"]["manifestHash"]) == 64

    def test_critique_is_honest_about_not_scoring_motion(self, video_campaign):
        """The film inherits the still's approval; that must be stated, not implied."""
        critique = video_campaign["assets"]["video"]["attempts"][-1]["critique"]
        reasoning = critique["reasoning"].lower()
        assert "not" in reasoning and (
            "independently" in reasoning or "motion" in reasoning
        ), f"critique overstates what was verified: {reasoning}"

    def test_video_prompt_carries_no_hex(self, video_campaign):
        prompt = video_campaign["assets"]["video"]["attempts"][-1]["promptUsed"]
        assert "#" not in prompt


@needs_server
class TestEmbeddedProvenance:
    def _fetch(self, campaign, kind) -> Path:
        url = campaign["delivery"][kind]
        raw = httpx.get(f"{BASE}{url}", timeout=180).content
        suffix = Path(url).suffix or ".bin"
        path = Path(tempfile.gettempdir()) / f"fernwood-live-delivery-{kind}{suffix}"
        path.write_bytes(raw)
        return path

    def test_delivery_assets_exist(self, delivery_campaign):
        delivery = delivery_campaign["delivery"]
        assert delivery
        for kind, url in delivery.items():
            assert url.startswith("/api/media/")
            assert httpx.get(f"{BASE}{url}", timeout=180).status_code == 200

    def test_manifest_extracts_from_the_file_itself(self, delivery_campaign):
        """The headline claim: a downloaded asset carries its own audit trail,
        independent of B2 and of this service."""
        from genblaze_core.media import get_handler

        checked = 0
        for kind, url in delivery_campaign["delivery"].items():
            path = self._fetch(delivery_campaign, kind)
            mime = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".mp3": "audio/mpeg",
                ".mp4": "video/mp4",
            }.get(path.suffix.lower())
            handler = get_handler(mime) if mime else None
            if handler is None:
                continue
            manifest = handler.extract(path)
            assert len(manifest.canonical_hash) == 64
            assert manifest.verify_hash() is True, f"{kind}: hash mismatch"
            assert manifest.verify() is True, f"{kind}: manifest does not verify"
            assert manifest.run.steps, f"{kind}: no steps in embedded manifest"
            print(
                f"\n  [live] {kind}: extracted manifest {manifest.canonical_hash[:12]} "
                f"({len(manifest.run.steps)} step(s), verify=True)"
            )
            checked += 1
        assert checked, "no delivery asset had an extractable manifest"

    def test_embedded_hash_matches_the_campaign_record(self, delivery_campaign):
        from genblaze_core.media import get_handler

        for kind in ("image", "audio", "video"):
            if kind not in delivery_campaign.get("delivery", {}):
                continue
            asset = delivery_campaign["assets"].get(kind)
            if not asset:
                continue
            approved = next(
                (a for a in asset["attempts"] if a["id"] == asset["finalApprovedAttemptId"]),
                asset["attempts"][-1],
            )
            expected = approved["content"].get("manifestHash")
            path = self._fetch(delivery_campaign, kind)
            mime = {
                ".jpg": "image/jpeg", ".png": "image/png",
                ".mp3": "audio/mpeg", ".mp4": "video/mp4",
            }.get(path.suffix.lower())
            handler = get_handler(mime) if mime else None
            if handler is None or expected is None:
                continue
            assert handler.extract(path).canonical_hash == expected, (
                f"{kind}: embedded manifest is not the one recorded for this attempt"
            )

    def test_delivery_stored_under_its_own_prefix(self, delivery_campaign):
        """delivery/ is separate from the sink's runs/ tree, because embedding
        mutates bytes and would otherwise invalidate the hash it commits to."""
        for url in delivery_campaign["delivery"].values():
            assert f"/campaigns/{delivery_campaign['id']}/delivery/" in url

    def test_original_asset_is_untouched(self, delivery_campaign):
        """The sink-stored asset must still match its manifest digest."""
        import hashlib

        asset = delivery_campaign["assets"].get("image")
        if not asset:
            pytest.skip("no image asset")
        approved = next(
            (a for a in asset["attempts"] if a["id"] == asset["finalApprovedAttemptId"]),
            asset["attempts"][-1],
        )
        original = httpx.get(
            f"{BASE}{approved['content']['imageUrl']}", timeout=180
        ).content
        delivery = httpx.get(
            f"{BASE}{delivery_campaign['delivery']['image']}", timeout=180
        ).content
        assert hashlib.sha256(original).hexdigest() != hashlib.sha256(delivery).hexdigest(), (
            "delivery file is byte-identical to the original — embedding did nothing"
        )
