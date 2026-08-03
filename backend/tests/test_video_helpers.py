"""MP4 duration parsing and the public-URL contract.

Both of these were live bugs:
  * the mvhd parser skipped the 3-byte flags field, so duration came back None
  * manifest_uri was stored as a raw B2 URL for image/audio/copy while video
    stored an /api/media URL — so provenance embedding could not resolve the
    manifest key and silently embedded nothing for those assets
"""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path

import pytest

# Moved to app/pipeline/assemble.py when the single-still film track was
# replaced by the multi-shot advertisement pipeline. Same parser, same bug
# it guards against.
from app.pipeline.assemble import (
    probe_duration_from_container as _probe_video_duration,
)


def _mvhd(version: int, timescale: int, duration: int) -> bytes:
    """Minimal MP4 fragment containing a well-formed mvhd box."""
    body = b"mvhd" + bytes([version]) + b"\x00\x00\x00"  # version + 3 flag bytes
    if version == 1:
        body += b"\x00" * 16  # creation(8) + modification(8)
        body += struct.pack(">I", timescale)
        body += struct.pack(">Q", duration)
    else:
        body += b"\x00" * 8  # creation(4) + modification(4)
        body += struct.pack(">I", timescale)
        body += struct.pack(">I", duration)
    return b"\x00\x00\x00\x20ftypisom" + b"\x00" * 16 + body + b"\x00" * 32


@pytest.fixture
def tmp_mp4(tmp_path):
    def _write(data: bytes) -> Path:
        p = tmp_path / "clip.mp4"
        p.write_bytes(data)
        return p

    return _write


class TestMp4DurationParsing:
    def test_version_0_box(self, tmp_mp4):
        assert _probe_video_duration(tmp_mp4(_mvhd(0, 1000, 6000))) == 6.0

    def test_version_1_box(self, tmp_mp4):
        assert _probe_video_duration(tmp_mp4(_mvhd(1, 600, 3600))) == 6.0

    def test_non_integer_duration(self, tmp_mp4):
        """Real clips are rarely exactly N seconds — 5.88s was observed live."""
        assert _probe_video_duration(tmp_mp4(_mvhd(0, 15360, 90317))) == pytest.approx(
            5.88, abs=0.01
        )

    def test_flags_field_is_not_skipped(self, tmp_mp4):
        """Regression: reading 4 bytes too early takes the modification time as
        the timescale, which yields None or nonsense."""
        d = _probe_video_duration(tmp_mp4(_mvhd(0, 1000, 12000)))
        assert d == 12.0

    def test_zero_timescale_is_safe(self, tmp_mp4):
        assert _probe_video_duration(tmp_mp4(_mvhd(0, 0, 6000))) is None

    def test_missing_mvhd_returns_none(self, tmp_mp4):
        assert _probe_video_duration(tmp_mp4(b"not an mp4 at all")) is None

    def test_missing_file_returns_none(self):
        assert _probe_video_duration(Path("/nonexistent/clip.mp4")) is None

    def test_none_path_returns_none(self):
        assert _probe_video_duration(None) is None


class TestManifestUriContract:
    """Every URL handed to the frontend must be an /api/media path.

    Provenance embedding derives the storage key by stripping that prefix, so a
    raw B2 URL leaves a full https:// string that is not a key — which is
    exactly how image and audio embedding failed silently.
    """

    def test_all_tracks_route_manifest_uri_through_public_media_url(self):
        source = Path(__file__).resolve().parent.parent / "app" / "pipeline" / "tracks.py"
        text = source.read_text()
        for raw in (
            "manifest_uri=result.manifest.manifest_uri,",
            "manifest_uri=script_result.manifest.manifest_uri,",
            "content.manifest_uri = tts_result.manifest.manifest_uri\n",
        ):
            assert raw not in text, (
                f"raw manifest URI assigned without public_media_url(): {raw!r}"
            )
        assert text.count("public_media_url(") >= 5

    def test_public_media_url_strips_to_a_usable_key(self):
        from app.storage.factory import get_backend, public_media_url

        backend = get_backend()
        key = "campaigns/c1/runs/x/manifest.json"
        public = public_media_url(backend.get_durable_url(key))
        assert public == f"/api/media/{key}"
        assert public.removeprefix("/api/media/") == key
