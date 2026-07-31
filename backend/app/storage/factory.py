"""Backend + sink construction. This is the ONLY place that knows whether we
are on local disk or Backblaze B2 — flipping FERNWOOD_STORAGE=b2 changes
nothing else in the codebase."""

from __future__ import annotations

import logging
from functools import lru_cache

from genblaze_core import KeyStrategy, ObjectStorageSink
from genblaze_core.storage.base import StorageBackend

from app.config import get_settings
from app.storage.backends import LocalDiskBackend

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_backend() -> StorageBackend:
    s = get_settings()
    if s.fernwood_storage.lower() == "b2":
        if not s.has_b2:
            raise RuntimeError(
                "FERNWOOD_STORAGE=b2 but B2_KEY_ID / B2_APP_KEY are unset."
            )
        from genblaze_s3 import S3StorageBackend

        # preflight=True fails loudly at construction on bad credentials
        # rather than silently at the first upload, mid-demo.
        logger.info("Storage backend: Backblaze B2 bucket=%s", s.b2_bucket)
        return S3StorageBackend.for_backblaze(
            s.b2_bucket,
            region=s.b2_region,
            key_id=s.b2_key_id,
            app_key=s.b2_app_key,
            auto_lifecycle=False,
            preflight=True,
        )

    logger.info("Storage backend: local disk at %s", s.local_root)
    return LocalDiskBackend(
        root=s.local_root,
        media_base_url=f"{s.public_api_base}/api/media",
    )


def make_sink(campaign_id: str) -> ObjectStorageSink:
    """A FRESH sink per Pipeline.run().

    ObjectStorageSink is single-use — Pipeline.run() closes it in a finally
    block, so reusing one across the retry attempts fails on attempt 2.

    key_strategy must be passed explicitly: the constructor default is
    CONTENT_ADDRESSABLE, which scatters one campaign across
    {prefix}/assets/{sha[:2]}/... and {prefix}/manifests/. HIERARCHICAL keeps
    a campaign's whole provenance tree under one browsable folder, which is
    what you want when showing the B2 console to a judge.
    """
    return ObjectStorageSink(
        get_backend(),
        prefix=f"campaigns/{campaign_id}",
        key_strategy=KeyStrategy.HIERARCHICAL,
    )


def public_media_url(asset_url: str) -> str:
    """Rewrite any storage URL into a stable /api/media/{key} URL.

    Applied to every URL the frontend sees, in BOTH storage modes. That makes
    the storage backend invisible to React, and means campaign.json files
    written under local mode keep working after the switch to B2 (where the
    bucket may be private and the raw durable URL would 403).
    """
    backend = get_backend()
    try:
        key = backend.key_from_url(asset_url)
    except Exception:  # noqa: BLE001 - never let URL rewriting break a run
        key = None
    if key:
        return f"/api/media/{key}"
    return asset_url
