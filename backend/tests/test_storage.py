"""Storage backend, sink integration, and the campaign index."""

from __future__ import annotations

import hashlib
import json

import pytest
from genblaze_core import Modality, Pipeline
from genblaze_core.models.asset import Asset as GbAsset
from genblaze_core.providers import SyncProvider
from genblaze_core.storage.errors import StorageError

from app.config import SCRATCH_DIR
from app.domain.models import Campaign, CampaignAssets, ColorPreference
from app.storage import index
from app.storage.backends import LocalDiskBackend
from app.storage.factory import get_backend, make_sink, public_media_url


class TestLocalDiskBackend:
    def _backend(self, tmp_path) -> LocalDiskBackend:
        return LocalDiskBackend(tmp_path / "b", "http://testserver/api/media")

    def test_put_returns_key_not_url(self, tmp_path):
        """StorageBackend.put contract: returns the storage KEY."""
        b = self._backend(tmp_path)
        assert b.put("a/b.txt", b"hi") == "a/b.txt"

    def test_roundtrip(self, tmp_path):
        b = self._backend(tmp_path)
        b.put("x/y.json", b'{"a":1}', content_type="application/json")
        assert b.get("x/y.json") == b'{"a":1}'
        assert b.exists("x/y.json")
        assert b.content_type_for("x/y.json") == "application/json"

    def test_delete_removes_object_and_sidecar(self, tmp_path):
        b = self._backend(tmp_path)
        b.put("k.bin", b"z", content_type="application/octet-stream")
        b.delete("k.bin")
        assert not b.exists("k.bin")
        assert b.content_type_for("k.bin") is None

    def test_missing_key_raises_storage_error(self, tmp_path):
        with pytest.raises(StorageError):
            self._backend(tmp_path).get("nope.txt")

    def test_durable_url_is_browser_loadable(self, tmp_path):
        """This is what lands in Asset.url and flows to AttemptContent.imageUrl."""
        b = self._backend(tmp_path)
        assert b.get_durable_url("c/a.png") == "http://testserver/api/media/c/a.png"

    def test_key_from_url_is_inverse_of_durable_url(self, tmp_path):
        b = self._backend(tmp_path)
        for key in ("a.png", "campaigns/c1/runs/x/assets/y.png", "with space.png"):
            assert b.key_from_url(b.get_durable_url(key)) == key

    def test_key_from_foreign_url_is_none(self, tmp_path):
        assert self._backend(tmp_path).key_from_url("https://elsewhere/x.png") is None

    @pytest.mark.parametrize("evil", ["../escape.txt", "a/../../escape.txt"])
    def test_path_traversal_blocked(self, tmp_path, evil):
        with pytest.raises(StorageError):
            self._backend(tmp_path).put(evil, b"x")

    def test_list_returns_listpage_and_skips_sidecars(self, tmp_path):
        b = self._backend(tmp_path)
        b.put("campaigns/c1/campaign.json", b"{}", content_type="application/json")
        b.put("campaigns/c2/campaign.json", b"{}", content_type="application/json")
        page = b.list("campaigns/")
        keys = {e.key for e in page.entries}
        assert keys == {"campaigns/c1/campaign.json", "campaigns/c2/campaign.json"}
        assert page.next_token is None
        assert not any(k.endswith(".ctype") for k in keys)

    def test_list_of_missing_prefix_is_empty(self, tmp_path):
        assert self._backend(tmp_path).list("nothing/").entries == ()


class _FileProvider(SyncProvider):
    """Writes to the scratch dir and emits a file:// asset, like the real ones."""

    name = "test-file"

    def generate(self, step, config=None):
        SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
        payload = f"bytes::{step.prompt}".encode()
        out = SCRATCH_DIR / f"{step.step_id}.json"
        out.write_bytes(payload)
        step.assets.append(
            GbAsset(
                url=out.resolve().as_uri(),
                media_type="application/json",
                sha256=hashlib.sha256(payload).hexdigest(),
                size_bytes=len(payload),
                metadata={"text": step.prompt or ""},
            )
        )
        return step


class TestSinkIntegration:
    """The path that makes provenance real. Covers three landmines at once:
    file:// assets must live under the temp dir, `text:` URLs would fail the
    upload, and manifests need a sha256 on every asset to verify."""

    def _run(self, campaign_id="camp-test"):
        return (
            Pipeline("t", tenant_id="fernwood", preflight=False)
            .step(
                _FileProvider(),
                model="m",
                prompt="hello",
                modality=Modality.TEXT,
                metadata={"attempt_number": 1},
            )
            .run(sink=make_sink(campaign_id), timeout=60, raise_on_failure=True)
        )

    def test_manifest_verifies(self):
        assert self._run().manifest.verify() is True

    def test_manifest_hash_is_stable_sha256(self):
        m = self._run().manifest
        assert len(m.canonical_hash) == 64
        assert m.verify_hash() is True

    def test_asset_url_rewritten_to_backend_url(self):
        asset = self._run().run.steps[0].assets[0]
        assert asset.url.startswith("http://testserver/api/media/")
        assert asset.sha256 and len(asset.sha256) == 64

    def test_public_media_url_is_relative(self):
        """Storage mode must be invisible to the frontend."""
        asset = self._run().run.steps[0].assets[0]
        assert public_media_url(asset.url).startswith("/api/media/")

    def test_hierarchical_layout_groups_by_campaign(self):
        result = self._run("camp-xyz")
        key = get_backend().key_from_url(result.manifest.manifest_uri)
        assert key.startswith("campaigns/camp-xyz/runs/")
        assert key.endswith("manifest.json")

    def test_manifest_readable_back_from_storage(self):
        result = self._run()
        b = get_backend()
        key = b.key_from_url(result.manifest.manifest_uri)
        assert json.loads(b.get(key).decode())["canonical_hash"] == (
            result.manifest.canonical_hash
        )

    def test_each_run_gets_a_distinct_manifest(self):
        """One manifest per ATTEMPT is the whole provenance story."""
        a, b = self._run("camp-1").manifest, self._run("camp-1").manifest
        assert a.manifest_uri != b.manifest_uri


class TestCampaignIndex:
    def _campaign(self, cid="camp-1", brand="Brand") -> Campaign:
        return Campaign(
            id=cid,
            brand_name=brand,
            product_service="P",
            target_audience="T",
            colors=ColorPreference(primary="#1", secondary="#2", accent="#3"),
            created_at="2026-08-01T00:00:00Z",
            updated_at="2026-08-01T00:00:00Z",
            status="completed",
            assets=CampaignAssets(),
        )

    def test_save_then_get(self):
        index.save_campaign(self._campaign())
        got = index.get_campaign("camp-1")
        assert got["brandName"] == "Brand"

    def test_missing_campaign_is_none(self):
        assert index.get_campaign("nope") is None

    def test_listing_is_newest_first(self):
        index.save_campaign(self._campaign("camp-1", "First"))
        index.save_campaign(self._campaign("camp-2", "Second"))
        rows, source = index.list_campaigns()
        assert source == "ok"
        assert [r["id"] for r in rows] == ["camp-2", "camp-1"]

    def test_resave_does_not_duplicate(self):
        index.save_campaign(self._campaign("camp-1", "V1"))
        index.save_campaign(self._campaign("camp-1", "V2"))
        rows, _ = index.list_campaigns()
        assert len(rows) == 1
        assert rows[0]["brandName"] == "V2"

    def test_delete_removes_from_index(self):
        index.save_campaign(self._campaign("camp-1"))
        index.delete_campaign("camp-1")
        rows, _ = index.list_campaigns()
        assert rows == []

    def test_empty_storage_lists_empty_not_error(self):
        rows, source = index.list_campaigns()
        assert rows == [] and source == "ok"

    def test_rebuild_index_self_heals(self):
        """If the rollup is lost, scanning campaign.json files restores it."""
        index.save_campaign(self._campaign("camp-1"))
        index.save_campaign(self._campaign("camp-2"))
        get_backend().delete(index.INDEX_KEY)
        rebuilt = index.rebuild_index()
        assert {r["id"] for r in rebuilt} == {"camp-1", "camp-2"}
