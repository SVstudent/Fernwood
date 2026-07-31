"""Media serving.

The frontend only ever sees /api/media/{key} URLs, in both storage modes, so it
never learns whether the bytes live on local disk or in B2. In local mode we
serve the bytes; in B2 mode we redirect to a short-lived presigned URL, which
also keeps a private bucket working.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse, Response

from app.config import get_settings
from app.storage.backends import LocalDiskBackend
from app.storage.factory import get_backend

logger = logging.getLogger(__name__)
router = APIRouter(tags=["media"])


@router.get("/media/{key:path}")
async def get_media(key: str):
    if ".." in key or key.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid key")

    backend = get_backend()

    if not isinstance(backend, LocalDiskBackend):
        try:
            url = await asyncio.to_thread(backend.get_url, key, expires_in=3600)
            return RedirectResponse(url, status_code=307)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Presign failed for %s: %s", key, exc)
            raise HTTPException(status_code=404, detail="Not found") from exc

    try:
        data = await asyncio.to_thread(backend.get, key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail="Not found") from exc

    ctype = backend.content_type_for(key) or mimetypes.guess_type(key)[0] or "application/octet-stream"
    return Response(
        content=data,
        media_type=ctype,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/storage-mode")
async def storage_mode() -> dict:
    return {"mode": get_settings().fernwood_storage}
