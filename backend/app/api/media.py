"""Media serving.

The frontend only ever sees /api/media/{key} URLs, in both storage modes, so it
never learns whether the bytes live on local disk or in B2.

WHY WE PROXY THE BYTES INSTEAD OF REDIRECTING TO B2:
An earlier version issued a 307 to a presigned B2 URL. Images survived that
(<img> tolerates cross-origin redirects), but <audio> did not — it stalled at
readyState HAVE_NOTHING / networkState NETWORK_LOADING and never fired
loadedmetadata, because the bucket is private with no CORS rules and media
elements will not follow an opaque cross-origin redirect. Proxying keeps
everything same-origin, so no bucket CORS configuration is required and the
bucket can stay private.

Range requests are honoured because <audio> issues them for seeking and for
duration probing; without Range support the transport shows no duration.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.config import get_settings
from app.storage.backends import LocalDiskBackend
from app.storage.factory import get_backend

logger = logging.getLogger(__name__)
router = APIRouter(tags=["media"])

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def _content_type(key: str) -> str:
    backend = get_backend()
    if isinstance(backend, LocalDiskBackend):
        sidecar = backend.content_type_for(key)
        if sidecar:
            return sidecar
    return mimetypes.guess_type(key)[0] or "application/octet-stream"


@router.get("/media/{key:path}")
async def get_media(key: str, request: Request):
    if ".." in key or key.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid key")

    backend = get_backend()
    try:
        data = await asyncio.to_thread(backend.get, key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("media miss for %s: %s", key, exc)
        raise HTTPException(status_code=404, detail="Not found") from exc

    media_type = _content_type(key)
    total = len(data)
    headers = {
        "Cache-Control": "public, max-age=31536000, immutable",
        "Accept-Ranges": "bytes",
    }

    range_header = request.headers.get("range")
    if range_header:
        match = _RANGE_RE.match(range_header.strip())
        if match:
            raw_start, raw_end = match.group(1), match.group(2)
            if raw_start:
                start = int(raw_start)
                end = int(raw_end) if raw_end else total - 1
            else:
                # suffix form: bytes=-N  (the last N bytes)
                length = int(raw_end or 0)
                start = max(0, total - length)
                end = total - 1
            if start >= total:
                return Response(
                    status_code=416,
                    headers={**headers, "Content-Range": f"bytes */{total}"},
                )
            end = min(end, total - 1)
            chunk = data[start : end + 1]
            return Response(
                content=chunk,
                status_code=206,
                media_type=media_type,
                headers={
                    **headers,
                    "Content-Range": f"bytes {start}-{end}/{total}",
                    "Content-Length": str(len(chunk)),
                },
            )

    return Response(content=data, media_type=media_type, headers=headers)


@router.get("/storage-mode")
async def storage_mode() -> dict:
    return {"mode": get_settings().fernwood_storage}
