"""SSE progress stream.

Replays buffered events before attaching to the live queue, so a reconnecting
browser never loses frames. Honours both the Last-Event-ID header (sent
automatically by EventSource on auto-reconnect) and a ?from= query param (for a
fresh EventSource after a component remount, which does not send the header).
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.runtime.registry import REGISTRY

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stream"])


@router.get("/campaigns/{campaign_id}/stream")
async def stream(campaign_id: str, request: Request):
    run = REGISTRY.get(campaign_id)
    if run is None:
        raise HTTPException(status_code=404, detail="No such run")

    last_seen = -1
    header = request.headers.get("last-event-id")
    if header and header.isdigit():
        last_seen = int(header)
    elif (q := request.query_params.get("from")) and q.lstrip("-").isdigit():
        last_seen = int(q)

    queue = REGISTRY.subscribe(run)

    async def gen():
        nonlocal last_seen
        try:
            # 1) replay anything the client missed
            for event in run.since(last_seen):
                last_seen = event.seq
                yield {
                    "id": str(event.seq),
                    "event": event.name,
                    "data": json.dumps(event.data),
                }

            # 2) if the run already finished, we're done
            if run.done:
                return

            # 3) live tail
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    # sse-starlette emits its own pings, but an explicit comment
                    # keeps intermediaries from buffering the connection closed.
                    yield {"comment": "keepalive"}
                    continue

                if event.seq <= last_seen:
                    continue
                last_seen = event.seq
                yield {
                    "id": str(event.seq),
                    "event": event.name,
                    "data": json.dumps(event.data),
                }
                if event.name in ("done", "error"):
                    break
        finally:
            REGISTRY.unsubscribe(run, queue)

    return EventSourceResponse(
        gen(),
        ping=15,
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Stops nginx-style proxies buffering the stream into oblivion.
            "X-Accel-Buffering": "no",
        },
    )
