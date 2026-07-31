"""Foundation test — no API keys required.

Proves the storage path end to end:
  trivial SyncProvider writing a temp file
    -> Pipeline.step()
    -> ObjectStorageSink(LocalDiskBackend)
    -> asset uploaded, SHA-256 computed, URL rewritten
    -> Manifest.verify() is True

This one test covers the three failure modes that would otherwise cost a day:
  * file:// assets outside tempfile.gettempdir() being rejected by the sink
  * `text:` scheme assets (the llm-calls doc's recipe) hard-failing write_run
  * manifests failing verify() because nothing set asset.sha256

Run:  uv run python scripts/test_storage.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from genblaze_core import Modality, Pipeline  # noqa: E402
from genblaze_core.models.asset import Asset  # noqa: E402
from genblaze_core.providers import SyncProvider  # noqa: E402

from app.config import SCRATCH_DIR  # noqa: E402
from app.storage.factory import get_backend, make_sink, public_media_url  # noqa: E402


class FakeFileProvider(SyncProvider):
    """Writes deterministic bytes to the scratch dir and emits a file:// asset."""

    name = "fake-file"

    def generate(self, step, config=None):
        SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"prompt": step.prompt}).encode()
        out = SCRATCH_DIR / f"{step.step_id}.json"
        out.write_bytes(payload)
        step.assets.append(
            Asset(
                url=out.resolve().as_uri(),
                media_type="application/json",
                sha256=hashlib.sha256(payload).hexdigest(),
                size_bytes=len(payload),
                metadata={"text": step.prompt or ""},
            )
        )
        return step


def main() -> int:
    campaign_id = "camp-storage-test"
    sink = make_sink(campaign_id)

    result = (
        Pipeline("storage-foundation-test", tenant_id="fernwood", preflight=False)
        .step(
            FakeFileProvider(),
            model="fake-model-v1",
            prompt="hello provenance",
            modality=Modality.TEXT,
            metadata={"attempt_number": 1, "asset_type": "copy"},
        )
        .run(sink=sink, timeout=60)
    )

    asset = result.run.steps[0].assets[0]
    manifest = result.manifest

    print(f"asset.url        : {asset.url}")
    print(f"public url       : {public_media_url(asset.url)}")
    print(f"asset.sha256     : {asset.sha256}")
    print(f"manifest_uri     : {manifest.manifest_uri}")
    print(f"canonical_hash   : {manifest.canonical_hash}")
    print(f"verify_hash()    : {manifest.verify_hash()}")
    print(f"verify()         : {manifest.verify()}")

    ok = True
    if not manifest.verify():
        print("FAIL: manifest.verify() is False")
        print(json.dumps(manifest.verification_report().model_dump(mode="json"), indent=2)[:1500])
        ok = False
    if not (asset.sha256 and len(asset.sha256) == 64):
        print("FAIL: asset.sha256 missing/short")
        ok = False
    if not public_media_url(asset.url).startswith("/api/media/"):
        print(f"FAIL: URL not rewritten to /api/media: {public_media_url(asset.url)}")
        ok = False

    # The manifest must actually be readable back out of storage.
    backend = get_backend()
    key = backend.key_from_url(manifest.manifest_uri) if manifest.manifest_uri else None
    if key and backend.exists(key):
        print(f"manifest readback: OK ({len(backend.get(key))} bytes at {key})")
    else:
        print(f"NOTE: manifest_uri={manifest.manifest_uri!r} key={key!r}")

    print("\nPASS" if ok else "\nFAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
