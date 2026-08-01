"""HTTP surface: endpoints, SSE framing, replay, and media serving."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.runtime.registry import REGISTRY, Registry
from app.storage import index


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class TestHealth:
    def test_reports_configuration(self, client):
        body = client.get("/api/health").json()
        assert body["storage"]["mode"] == "local"
        for key in ("tokenrouter", "elevenlabs", "pipeline", "warnings"):
            assert key in body

    def test_exposes_resolved_models(self, client):
        tr = client.get("/api/health").json()["tokenrouter"]
        assert tr["imageModel"] and tr["visionModel"] and tr["chatModel"]


class TestCampaignEndpoints:
    def test_list_empty_is_ok_not_error(self, client):
        """Empty storage must not look like a failure — the frontend only falls
        back to preseeded samples when source == 'unavailable'."""
        body = client.get("/api/campaigns").json()
        assert body["campaigns"] == [] and body["source"] == "ok"

    def test_get_unknown_campaign_404s(self, client):
        assert client.get("/api/campaigns/does-not-exist").status_code == 404

    def test_stream_for_unknown_run_404s(self, client):
        assert client.get("/api/campaigns/nope/stream").status_code == 404

    def test_post_validates_the_brief(self, client):
        assert client.post("/api/campaigns", json={"brandName": "only"}).status_code == 422

    def test_delete_is_idempotent(self, client):
        assert client.delete("/api/campaigns/never-existed").status_code == 204

    def test_saved_campaign_is_listed_and_fetchable(self, client):
        from app.domain.models import Campaign, CampaignAssets, ColorPreference

        index.save_campaign(
            Campaign(
                id="camp-api",
                brand_name="APITest",
                product_service="P",
                target_audience="T",
                colors=ColorPreference(primary="#1", secondary="#2", accent="#3"),
                created_at="2026-08-01T00:00:00Z",
                updated_at="2026-08-01T00:00:00Z",
                status="completed",
                assets=CampaignAssets(),
            )
        )
        rows = client.get("/api/campaigns").json()["campaigns"]
        assert [r["id"] for r in rows] == ["camp-api"]
        assert client.get("/api/campaigns/camp-api").json()["brandName"] == "APITest"

    def test_delete_does_not_resurrect_on_reload(self, client):
        """Regression: deleting only the index entry let rebuild_index() find
        the orphaned campaign.json and bring the campaign back."""
        from app.domain.models import Campaign, CampaignAssets, ColorPreference

        index.save_campaign(
            Campaign(
                id="camp-del",
                brand_name="Gone",
                product_service="P",
                target_audience="T",
                colors=ColorPreference(primary="#1", secondary="#2", accent="#3"),
                created_at="2026-08-01T00:00:00Z",
                updated_at="2026-08-01T00:00:00Z",
                assets=CampaignAssets(),
            )
        )
        client.delete("/api/campaigns/camp-del")
        assert client.get("/api/campaigns").json()["campaigns"] == []
        assert client.get("/api/campaigns/camp-del").status_code == 404


class TestMedia:
    def test_serves_stored_bytes_with_content_type(self, client):
        from app.storage.factory import get_backend

        get_backend().put("campaigns/c/a.json", b'{"x":1}', content_type="application/json")
        r = client.get("/api/media/campaigns/c/a.json")
        assert r.status_code == 200
        assert r.json() == {"x": 1}
        assert r.headers["content-type"].startswith("application/json")

    def test_immutable_cache_header(self, client):
        from app.storage.factory import get_backend

        get_backend().put("campaigns/c/b.txt", b"hi", content_type="text/plain")
        assert "immutable" in client.get("/api/media/campaigns/c/b.txt").headers["cache-control"]

    def test_missing_media_404s(self, client):
        assert client.get("/api/media/campaigns/none/x.png").status_code == 404

    @pytest.mark.parametrize("evil", ["../../../etc/passwd", "..%2F..%2Fetc%2Fpasswd"])
    def test_path_traversal_rejected(self, client, evil):
        assert client.get(f"/api/media/{evil}").status_code in (400, 404)


class TestSSE:
    """The stream is how the UI learns anything; framing and replay are
    load-bearing for a run that outlives a page reload."""

    def _seed(self, campaign_id="camp-sse"):
        reg = REGISTRY
        run = reg.create(campaign_id)
        reg.publish(campaign_id, "log", {"id": "l1", "title": "One"})
        reg.publish(campaign_id, "log", {"id": "l2", "title": "Two"})
        reg.publish(campaign_id, "done", {"status": "completed", "campaign": {"id": campaign_id}})
        return run

    def _parse(self, text):
        events, cur = [], {}
        for line in text.splitlines():
            if line.startswith("id:"):
                cur["id"] = line[3:].strip()
            elif line.startswith("event:"):
                cur["event"] = line[6:].strip()
            elif line.startswith("data:"):
                cur["data"] = json.loads(line[5:])
            elif not line.strip() and cur:
                events.append(cur)
                cur = {}
        if cur:
            events.append(cur)
        return events

    def test_replays_buffered_events_then_closes(self, client):
        self._seed()
        events = self._parse(client.get("/api/campaigns/camp-sse/stream").text)
        assert [e["event"] for e in events] == ["log", "log", "done"]
        assert [e["id"] for e in events] == ["0", "1", "2"]

    def test_from_query_resumes_after_seq(self, client):
        self._seed()
        events = self._parse(client.get("/api/campaigns/camp-sse/stream?from=0").text)
        assert [e["event"] for e in events] == ["log", "done"]

    def test_last_event_id_header_resumes(self, client):
        """EventSource sends this automatically on auto-reconnect."""
        self._seed()
        events = self._parse(
            client.get("/api/campaigns/camp-sse/stream", headers={"Last-Event-ID": "1"}).text
        )
        assert [e["event"] for e in events] == ["done"]

    def test_stream_headers_prevent_proxy_buffering(self, client):
        self._seed()
        h = client.get("/api/campaigns/camp-sse/stream").headers
        assert h["content-type"].startswith("text/event-stream")
        assert h.get("x-accel-buffering") == "no"
        assert "no-cache" in h.get("cache-control", "")


class TestRegistry:
    def test_events_get_monotonic_sequence_numbers(self):
        reg = Registry()
        reg.create("c")
        for i in range(5):
            reg.publish("c", "log", {"i": i})
        assert [e.seq for e in reg.get("c").events] == [0, 1, 2, 3, 4]

    def test_since_filters_by_sequence(self):
        reg = Registry()
        reg.create("c")
        for i in range(4):
            reg.publish("c", "log", {"i": i})
        assert [e.data["i"] for e in reg.get("c").since(1)] == [2, 3]

    def test_terminal_events_mark_run_done(self):
        reg = Registry()
        reg.create("c")
        reg.publish("c", "done", {"status": "completed", "campaign": {"id": "c"}})
        assert reg.get("c").done is True
        assert reg.get("c").finished_at is not None

    def test_error_event_also_terminal(self):
        reg = Registry()
        reg.create("c")
        reg.publish("c", "error", {"message": "boom"})
        assert reg.get("c").done is True

    def test_publish_to_unknown_run_is_noop(self):
        Registry().publish("ghost", "log", {})  # must not raise

    def test_campaign_snapshot_retained(self):
        reg = Registry()
        reg.create("c")
        reg.publish("c", "campaign", {"id": "c", "status": "running"})
        assert reg.get("c").campaign["status"] == "running"
