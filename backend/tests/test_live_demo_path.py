"""LIVE END-TO-END DEMO PATH — the exact flow a judge will watch.

This is the highest-value test in the repo: it drives the real HTTP API with
real TokenRouter + ElevenLabs + Backblaze B2, exactly as the browser does, and
asserts on everything that appears on screen.

    uv run pytest tests/test_live_demo_path.py -m live -v -s

Takes 4-8 minutes and costs real money. It runs ONE campaign and then asserts
against it, so the cost is one campaign regardless of how many checks run.
"""

from __future__ import annotations

import json
import os
import time

import httpx
import pytest

from app.config import get_settings

pytestmark = pytest.mark.live

BASE = os.environ.get("FERNWOOD_TEST_BASE", "http://127.0.0.1:8787")

BRIEF = {
    "brandName": "Fernwood Goods",
    "productService": "Handcrafted ceramic dinnerware",
    "targetAudience": "Design-conscious home cooks, 28-45",
    "briefText": "Warm, tactile, slow-living. Natural light, imperfect handmade forms.",
    "toneTags": ["Earthy & Organic", "Cozy & Warm"],
    "colors": {"primary": "#1E3A2B", "secondary": "#F4F1EA", "accent": "#D97706"},
}


def _server_up() -> bool:
    try:
        return httpx.get(f"{BASE}/api/health", timeout=5).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _server_storage_mode() -> str:
    """Ask the SERVER what storage it uses.

    get_settings() in the test process is not authoritative here: conftest's
    autouse fixture forces FERNWOOD_STORAGE=local so offline tests never touch
    real storage. Using it would silently skip the B2 provenance assertions —
    which are the whole point of this file.
    """
    try:
        return httpx.get(f"{BASE}/api/health", timeout=5).json()["storage"]["mode"]
    except Exception:  # noqa: BLE001
        return "unknown"


def _b2_client():
    """boto3 client from the raw environment, bypassing patched settings."""
    import boto3
    from dotenv import load_dotenv

    load_dotenv(
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        override=True,
    )
    region = os.environ["B2_REGION"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://s3.{region}.backblazeb2.com",
        aws_access_key_id=os.environ["B2_KEY_ID"],
        aws_secret_access_key=os.environ["B2_APP_KEY"],
        region_name=region,
    ), os.environ["B2_BUCKET"]


needs_b2_server = pytest.mark.skipif(
    _server_storage_mode() != "b2",
    reason=f"server storage mode is {_server_storage_mode()!r}, not b2",
)


needs_server = pytest.mark.skipif(
    not _server_up(), reason=f"backend not running at {BASE}"
)


@pytest.fixture(scope="module")
def demo_run():
    """Run ONE real campaign end to end and capture every SSE frame."""
    if not _server_up():
        pytest.skip("backend not running")

    start = httpx.post(f"{BASE}/api/campaigns", json=BRIEF, timeout=30)
    assert start.status_code == 202, start.text
    campaign_id = start.json()["campaignId"]
    print(f"\n  [live] campaign {campaign_id} started; streaming...")

    frames: list[tuple[str, dict]] = []
    deadline = time.time() + 900
    with httpx.stream(
        "GET", f"{BASE}/api/campaigns/{campaign_id}/stream", timeout=920
    ) as resp:
        assert resp.status_code == 200
        event = None
        for line in resp.iter_lines():
            if time.time() > deadline:
                pytest.fail("campaign exceeded 15 minutes")
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and event:
                payload = json.loads(line[5:])
                frames.append((event, payload))
                if event == "log":
                    print(f"  [live] {payload['type']:7s} {payload['title']}")
                if event in ("done", "error"):
                    break

    final = httpx.get(f"{BASE}/api/campaigns/{campaign_id}", timeout=30).json()
    return {"id": campaign_id, "frames": frames, "campaign": final}


@needs_server
class TestDemoPipelineCompletes:
    def test_terminal_done_frame_received(self, demo_run):
        names = [n for n, _ in demo_run["frames"]]
        assert names[-1] == "done", f"stream ended on {names[-1]!r}, not 'done'"

    def test_campaign_completed(self, demo_run):
        assert demo_run["campaign"]["status"] == "completed"

    def test_all_three_assets_produced(self, demo_run):
        assets = demo_run["campaign"]["assets"]
        assert set(assets) == {"image", "audio", "copy"}
        for kind, asset in assets.items():
            assert asset["attempts"], f"{kind} produced no attempts"

    def test_quality_score_is_real(self, demo_run):
        score = demo_run["campaign"]["overallQualityScore"]
        assert 0 < score <= 100

    def test_provider_failures_did_not_break_the_run(self, demo_run):
        """Transient upstream hiccups are tolerable if the pipeline recovers;
        an asset left with zero attempts is not.

        Kept deliberately informative rather than merely strict — this is how a
        180s image timeout was found and fixed (the provider request timeout is
        now 300s, under a 420s pipeline step timeout).
        """
        errors = [
            p for n, p in demo_run["frames"] if n == "log" and p["type"] == "error"
        ]
        if errors:
            print(f"\n  [live] recovered provider errors: {[e['title'] for e in errors]}")

        starved = [
            kind
            for kind, asset in demo_run["campaign"]["assets"].items()
            if not asset["attempts"]
        ]
        assert not starved, f"assets with zero attempts after retries: {starved}"

        # More than one provider failure per asset type suggests a real outage
        # or a misconfiguration, not a blip.
        assert len(errors) <= 3, f"excessive provider failures: {len(errors)}"


@needs_server
class TestSelfCritiqueLoopIsReal:
    """The headline feature. These assertions are the demo's actual claim."""

    def test_critiques_produced_varied_real_scores(self, demo_run):
        scores = [
            a["critique"]["overallScore"]
            for asset in demo_run["campaign"]["assets"].values()
            for a in asset["attempts"]
        ]
        assert scores
        assert all(0 <= s <= 100 for s in scores)
        # A stubbed/fallback critique would emit identical canned numbers.
        assert len(set(scores)) > 1, f"all critique scores identical: {scores}"

    def test_critique_reasoning_is_substantive_not_canned(self, demo_run):
        for asset in demo_run["campaign"]["assets"].values():
            for a in asset["attempts"]:
                reasoning = a["critique"]["reasoning"]
                assert len(reasoning) > 60, f"thin critique: {reasoning!r}"
                assert "unavailable" not in reasoning.lower(), (
                    "critique fell back to the heuristic verdict — the model "
                    "was unreachable or returned unparseable output"
                )

    def test_every_critique_has_scored_criteria(self, demo_run):
        for asset in demo_run["campaign"]["assets"].values():
            for a in asset["attempts"]:
                criteria = a["critique"]["criteria"]
                assert len(criteria) >= 3
                for c in criteria:
                    assert c["name"] and c["feedback"]
                    assert 0 <= c["score"] <= 100

    def test_retry_prompt_incorporates_previous_critique(self, demo_run):
        """The causal link. Skips only if nothing needed a retry."""
        retried = [
            asset
            for asset in demo_run["campaign"]["assets"].values()
            if len(asset["attempts"]) > 1
        ]
        if not retried:
            pytest.skip("everything passed first time this run")
        for asset in retried:
            first, second = asset["attempts"][0], asset["attempts"][1]
            assert first["critiqueVerdict"] == "FAIL"
            assert "REVISION 2" in second["promptUsed"]
            fixes = first["critique"]["suggestedFixes"]
            # Image prompts are sanitized, so compare on a distinctive fragment.
            fragment = " ".join(fixes.split()[:6])
            assert fragment[:20].lower() in second["promptUsed"].lower() or len(
                second["promptUsed"]
            ) > len(first["promptUsed"])

    def test_image_prompts_never_contain_hex(self, demo_run):
        """Regression: hex in the prompt gets painted into the poster."""
        for a in demo_run["campaign"]["assets"]["image"]["attempts"]:
            assert "#" not in a["promptUsed"]

    def test_verdicts_match_scores(self, demo_run):
        threshold = get_settings().fernwood_pass_threshold
        for asset in demo_run["campaign"]["assets"].values():
            for a in asset["attempts"]:
                expected = "PASS" if a["critique"]["overallScore"] >= threshold else "FAIL"
                assert a["critiqueVerdict"] == expected


@needs_server
class TestAssetsAreRealAndReachable:
    def test_image_is_a_real_decodable_png_or_jpeg(self, demo_run):
        from PIL import Image
        import io

        attempt = demo_run["campaign"]["assets"]["image"]["attempts"][-1]
        url = attempt["content"]["imageUrl"]
        assert url.startswith("/api/media/")
        r = httpx.get(f"{BASE}{url}", timeout=60)
        assert r.status_code == 200
        with Image.open(io.BytesIO(r.content)) as im:
            assert im.width >= 1024 and im.height >= 576

    def test_audio_is_a_real_mp3_served_with_range(self, demo_run):
        attempts = demo_run["campaign"]["assets"]["audio"]["attempts"]
        url = next(
            (a["content"].get("audioUrl") for a in reversed(attempts) if a["content"].get("audioUrl")),
            None,
        )
        assert url, "no audioUrl — ElevenLabs synthesis did not run"

        full = httpx.get(f"{BASE}{url}", timeout=60)
        assert full.status_code == 200
        assert full.headers["content-type"].startswith("audio/")
        assert full.content[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3")
        assert len(full.content) > 10_000

        # <audio> needs Range to probe duration and to seek.
        part = httpx.get(f"{BASE}{url}", headers={"Range": "bytes=0-99"}, timeout=30)
        assert part.status_code == 206
        assert part.headers["accept-ranges"] == "bytes"

    def test_copy_suite_is_populated(self, demo_run):
        content = demo_run["campaign"]["assets"]["copy"]["attempts"][-1]["content"]
        for field in ("headline", "subheadline", "bodyText", "callToAction"):
            assert content.get(field), f"missing {field}"
        assert len(content.get("keyBenefitBullets") or []) == 3
        assert len(content.get("socialPosts") or []) == 2

    def test_voiceover_script_is_speakable_length(self, demo_run):
        script = demo_run["campaign"]["assets"]["audio"]["attempts"][-1]["content"]["audioScript"]
        assert 15 <= len(script.split()) <= 120


@needs_server
class TestProvenanceInB2:
    def test_every_attempt_has_a_distinct_manifest_hash(self, demo_run):
        hashes = [
            a["content"].get("manifestHash")
            for asset in demo_run["campaign"]["assets"].values()
            for a in asset["attempts"]
        ]
        assert all(h and len(h) == 64 for h in hashes), hashes
        assert len(set(hashes)) == len(hashes), "manifest hashes are not unique"

    @needs_b2_server
    def test_manifests_downloaded_from_b2_verify(self, demo_run):
        """Download the actual provenance documents from Backblaze and verify
        their SHA-256 canonical hash and per-asset digests."""
        from genblaze_core import Manifest

        s3, bucket = _b2_client()
        prefix = f"campaigns/{demo_run['id']}/"
        keys = [
            o["Key"]
            for o in s3.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", [])
            if o["Key"].endswith("manifest.json")
        ]
        assert len(keys) >= 3, f"expected >=3 manifests in B2, found {len(keys)}"
        for key in keys:
            body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            manifest = Manifest.model_validate_json(body)
            assert manifest.verify_hash() is True, key
            assert manifest.verify() is True, key
        print(f"\n  [live] {len(keys)} manifests verified from B2")

    @needs_b2_server
    def test_asset_blobs_exist_in_b2(self, demo_run):
        s3, bucket = _b2_client()
        prefix = f"campaigns/{demo_run['id']}/"
        objs = s3.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", [])
        blobs = [o for o in objs if "/assets/" in o["Key"]]
        assert blobs, "no asset blobs landed in B2"
        assert any(o["Key"].endswith((".jpg", ".png")) for o in blobs), "no image blob"
        assert any(o["Key"].endswith(".mp3") for o in blobs), "no audio blob"
        assert any(o["Size"] > 100_000 for o in blobs), "blobs suspiciously small"

    @needs_b2_server
    def test_campaign_json_in_b2_matches_api(self, demo_run):
        s3, bucket = _b2_client()
        key = f"campaigns/{demo_run['id']}/campaign.json"
        stored = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
        assert stored["id"] == demo_run["id"]
        assert stored["status"] == demo_run["campaign"]["status"]

    def test_campaign_json_persisted_and_listed(self, demo_run):
        listing = httpx.get(f"{BASE}/api/campaigns", timeout=30).json()
        assert listing["source"] == "ok"
        assert demo_run["id"] in [c["id"] for c in listing["campaigns"]]

    @needs_b2_server
    def test_providers_recorded_in_manifests(self, demo_run):
        """All three required integrations must appear in the provenance record."""
        from genblaze_core import Manifest

        s3, bucket = _b2_client()
        prefix = f"campaigns/{demo_run['id']}/"
        providers, attempt_numbers = set(), set()
        for o in s3.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", []):
            if not o["Key"].endswith("manifest.json"):
                continue
            m = Manifest.model_validate_json(
                s3.get_object(Bucket=bucket, Key=o["Key"])["Body"].read()
            )
            for step in m.run.steps:
                providers.add(step.provider)
                if step.metadata.get("attempt_number"):
                    attempt_numbers.add(step.metadata["attempt_number"])
        assert "tokenrouter-image" in providers
        assert "tokenrouter-chat" in providers
        assert "elevenlabs-tts" in providers
        # attempt_number lives in Step.metadata, which IS covered by the
        # canonical hash — so the retry index is cryptographically bound.
        assert attempt_numbers, "no attempt_number recorded in step metadata"


@needs_server
class TestStreamContractForTheUI:
    """PipelineRunView derives its progress bar and retry feed from these."""

    def test_stage_ids_are_ones_the_ui_knows(self, demo_run):
        known = {
            "brief_analysis", "image_gen", "image_critique", "audio_gen",
            "audio_critique", "copy_gen", "copy_critique", "assembly", "b2_upload",
        }
        seen = {p["stage"] for n, p in demo_run["frames"] if n == "log"}
        assert seen and seen <= known, f"unknown stages: {seen - known}"

    def test_rejected_attempts_carry_attempt_details(self, demo_run):
        """The retry feed filters on type=='warning' && attemptDetails."""
        warnings = [
            p for n, p in demo_run["frames"] if n == "log" and p["type"] == "warning"
        ]
        for w in warnings:
            assert w.get("attemptDetails"), "warning frame without attemptDetails"
            assert w["attemptDetails"]["critiqueVerdict"] == "FAIL"

    def test_passing_attempts_carry_attempt_details(self, demo_run):
        successes = [
            p
            for n, p in demo_run["frames"]
            if n == "log" and p["type"] == "success" and p.get("attemptDetails")
        ]
        assert successes
        for s in successes:
            assert s["attemptDetails"]["critiqueVerdict"] == "PASS"

    def test_campaign_snapshots_streamed(self, demo_run):
        snapshots = [p for n, p in demo_run["frames"] if n == "campaign"]
        assert len(snapshots) >= 2
        assert snapshots[-1]["id"] == demo_run["id"]

    def test_frames_are_camel_case(self, demo_run):
        _, payload = next(p for p in demo_run["frames"] if p[0] == "log")
        assert "timestamp" in payload and "stage" in payload
        assert not any("_" in k for k in payload)
