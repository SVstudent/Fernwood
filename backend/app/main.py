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

from app.api import campaigns, health, media, stream
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

# The Vite dev server proxies /api here. CORS is the escape hatch: if SSE
# misbehaves through the proxy, point the frontend straight at :8000 by
# setting VITE_API_BASE and everything keeps working.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(campaigns.router, prefix="/api")
app.include_router(stream.router, prefix="/api")
app.include_router(media.router, prefix="/api")
