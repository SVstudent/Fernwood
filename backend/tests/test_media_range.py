"""Media proxying and HTTP Range support.

Regression cover for a real browser failure: serving media as a 307 redirect to
a presigned B2 URL left <audio> stuck at HAVE_NOTHING forever (private bucket,
no CORS, media elements will not follow the cross-origin redirect). We proxy the
bytes same-origin instead, and must honour Range because <audio> uses it to
probe duration and to seek.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage.factory import get_backend

PAYLOAD = bytes(range(256)) * 8  # 2048 bytes
KEY = "campaigns/c1/runs/x/assets/track.mp3"


@pytest.fixture
def client():
    with TestClient(app) as c:
        get_backend().put(KEY, PAYLOAD, content_type="audio/mpeg")
        yield c


class TestMediaProxy:
    def test_serves_bytes_not_a_redirect(self, client):
        """Must be 200 with the payload — never a 3xx to another origin."""
        r = client.get(f"/api/media/{KEY}", follow_redirects=False)
        assert r.status_code == 200
        assert r.content == PAYLOAD
        assert r.headers["content-type"].startswith("audio/mpeg")

    def test_advertises_range_support(self, client):
        r = client.get(f"/api/media/{KEY}")
        assert r.headers["accept-ranges"] == "bytes"

    def test_full_content_length(self, client):
        r = client.get(f"/api/media/{KEY}")
        assert int(r.headers["content-length"]) == len(PAYLOAD)


class TestRangeRequests:
    def test_open_ended_range(self, client):
        r = client.get(f"/api/media/{KEY}", headers={"Range": "bytes=0-"})
        assert r.status_code == 206
        assert r.content == PAYLOAD
        assert r.headers["content-range"] == f"bytes 0-{len(PAYLOAD)-1}/{len(PAYLOAD)}"

    def test_bounded_range(self, client):
        r = client.get(f"/api/media/{KEY}", headers={"Range": "bytes=10-19"})
        assert r.status_code == 206
        assert r.content == PAYLOAD[10:20]
        assert r.headers["content-range"] == f"bytes 10-19/{len(PAYLOAD)}"
        assert int(r.headers["content-length"]) == 10

    def test_suffix_range_last_n_bytes(self, client):
        """bytes=-N — used by players probing the tail for duration metadata."""
        r = client.get(f"/api/media/{KEY}", headers={"Range": "bytes=-64"})
        assert r.status_code == 206
        assert r.content == PAYLOAD[-64:]

    def test_range_past_end_is_clamped(self, client):
        r = client.get(f"/api/media/{KEY}", headers={"Range": "bytes=2040-999999"})
        assert r.status_code == 206
        assert r.content == PAYLOAD[2040:]

    def test_unsatisfiable_range_416(self, client):
        r = client.get(f"/api/media/{KEY}", headers={"Range": "bytes=99999-"})
        assert r.status_code == 416
        assert r.headers["content-range"] == f"bytes */{len(PAYLOAD)}"

    def test_malformed_range_falls_back_to_full(self, client):
        r = client.get(f"/api/media/{KEY}", headers={"Range": "rubbish"})
        assert r.status_code == 200
        assert r.content == PAYLOAD


class TestSecurity:
    @pytest.mark.parametrize("evil", ["../../../etc/passwd", "/etc/passwd"])
    def test_path_traversal_rejected(self, client, evil):
        assert client.get(f"/api/media/{evil}").status_code in (400, 404)

    def test_unknown_key_404(self, client):
        assert client.get("/api/media/campaigns/none/missing.mp3").status_code == 404
