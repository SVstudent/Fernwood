"""Embed provenance manifests into the delivered media files.

Genblaze can write a canonical, hash-verified manifest INTO an MP4/JPEG/PNG/MP3
container (`genblaze_core.media`). That makes a downloaded asset self-describing:
you can extract and verify its full generation history from the file alone,
without access to B2 or this service.

We write these as a separate `delivery/` tree rather than mutating the assets the
sink already stored, because those bytes are what the manifest's SHA-256 commits
to — rewriting them in place would invalidate the very hash being embedded.

    campaigns/{id}/delivery/image.jpg    <- approved key visual + manifest
    campaigns/{id}/delivery/audio.mp3    <- voiceover + manifest
    campaigns/{id}/delivery/video.mp4    <- brand film + manifest
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from genblaze_core import Manifest
from genblaze_core.media import get_handler

from app.storage.factory import get_backend

logger = logging.getLogger(__name__)

_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
}


def embed_into_delivery(
    *,
    campaign_id: str,
    asset_kind: str,
    source_key: str,
    manifest: Manifest,
    media_type: str,
) -> str | None:
    """Embed `manifest` into the stored asset and save it under delivery/.

    Returns the delivery key, or None if the format is unsupported or embedding
    failed. Never raises — a campaign must not fail because a container did not
    accept a metadata block.
    """
    handler = get_handler(media_type)
    if handler is None:
        logger.info("no media handler for %s; skipping embed", media_type)
        return None

    backend = get_backend()
    try:
        raw = backend.get(source_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read %s for embedding: %s", source_key, exc)
        return None

    ext = _EXT.get(media_type, Path(source_key).suffix or ".bin")
    tmp_dir = Path(tempfile.gettempdir()) / "fernwood" / "delivery"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    src = tmp_dir / f"{campaign_id}-{asset_kind}{ext}"
    src.write_bytes(raw)

    try:
        embedded = handler.embed(src, manifest)
        payload = Path(embedded).read_bytes()
        # Prove it round-trips before we publish it as the deliverable.
        recovered = handler.extract(embedded)
        if recovered.canonical_hash != manifest.canonical_hash:
            logger.warning(
                "embedded manifest did not round-trip for %s; skipping", asset_kind
            )
            return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("embed failed for %s (%s): %s", asset_kind, media_type, exc)
        return None

    key = f"campaigns/{campaign_id}/delivery/{asset_kind}{ext}"
    try:
        backend.put(key, payload, content_type=media_type)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not store delivery asset %s: %s", key, exc)
        return None

    logger.info(
        "embedded manifest %s into %s (%d bytes)",
        manifest.canonical_hash[:12],
        key,
        len(payload),
    )
    return key


def extract_manifest(path: str | Path, media_type: str) -> Manifest | None:
    """Read an embedded manifest back out of a media file, if present."""
    handler = get_handler(media_type)
    if handler is None:
        return None
    try:
        return handler.extract(path)
    except Exception:  # noqa: BLE001 - absent or unreadable metadata
        return None
