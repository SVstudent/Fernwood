"""Fernwood backend — FastAPI sidecar.

Run with:
    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

IMPORTANT: single worker only. The run registry and its SSE fan-out are
in-process, so --workers > 1 would let a client connect to a worker that has
never heard of its run.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import brain, campaigns, health, media, stream
from app.config import get_settings
from app.providers.client import probe_models
from app.runtime.registry import REGISTRY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("fernwood")


@asynccontextmanager
async def lifespan(app: FastAPI):
    REGISTRY.bind_loop(asyncio.get_running_loop())
    # Resolve which TokenRouter models this key can actually reach. Never
    # raises — a failed probe falls back to defaults and records a warning
    # surfaced by GET /api/health.
    await asyncio.to_thread(probe_models)
    yield


app = FastAPI(title="Fernwood Pipeline API", version="0.1.0", lifespan=lifespan)

# In development the Vite server proxies /api here, so CORS is unused. In
# production the frontend is served from another origin entirely (Vercel) and
# calls this API directly — so the deployed origin MUST be allowed or every
# request fails, including the SSE stream, which looks like a run that starts
# and then silently stops.
#
# allow_origin_regex covers Vercel preview deployments, which mint a new
# hostname per commit; pinning those by hand would break on every push.
_dev_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
]
_configured = [
    origin.strip()
    for origin in get_settings().fernwood_allowed_origins.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[*_dev_origins, *_configured],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    # The media endpoint serves video with Range requests; browsers need these
    # exposed or seeking in the <video> player breaks.
    expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
)

app.include_router(health.router, prefix="/api")
app.include_router(campaigns.router, prefix="/api")
app.include_router(stream.router, prefix="/api")
app.include_router(media.router, prefix="/api")
app.include_router(brain.router, prefix="/api")
