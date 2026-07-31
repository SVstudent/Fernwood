"""In-memory run registry + event fan-out for SSE.

Each run keeps an ordered event buffer so a browser that reconnects (tab reload,
laptop sleep, proxy hiccup) can replay from Last-Event-ID rather than losing the
run. Runs continue server-side regardless of whether anyone is listening.

Single-process only: do NOT run uvicorn with --workers > 1, or a client will
connect to a worker that has never heard of its run.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_RETAIN_SECONDS = 30 * 60
_MAX_EVENTS = 2000


@dataclass
class Event:
    seq: int
    name: str  # "log" | "campaign" | "done" | "error"
    data: dict[str, Any]


@dataclass
class Run:
    campaign_id: str
    events: list[Event] = field(default_factory=list)
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    done: bool = False
    finished_at: float | None = None
    campaign: dict[str, Any] | None = None

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def append(self, name: str, data: dict[str, Any]) -> Event:
        with self._lock:
            event = Event(seq=len(self.events), name=name, data=data)
            self.events.append(event)
            if len(self.events) > _MAX_EVENTS:
                del self.events[: len(self.events) - _MAX_EVENTS]
        return event

    def since(self, after_seq: int) -> list[Event]:
        with self._lock:
            return [e for e in self.events if e.seq > after_seq]


class Registry:
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Capture the event loop so worker threads can push to async queues."""
        self._loop = loop

    def create(self, campaign_id: str) -> Run:
        with self._lock:
            self._gc()
            run = Run(campaign_id=campaign_id)
            self._runs[campaign_id] = run
            return run

    def get(self, campaign_id: str) -> Run | None:
        return self._runs.get(campaign_id)

    def _gc(self) -> None:
        now = time.time()
        stale = [
            cid
            for cid, run in self._runs.items()
            if run.finished_at and now - run.finished_at > _RETAIN_SECONDS
        ]
        for cid in stale:
            self._runs.pop(cid, None)

    # -- publishing (called from the worker THREAD, not the event loop) --
    def publish(self, campaign_id: str, name: str, data: dict[str, Any]) -> None:
        run = self._runs.get(campaign_id)
        if run is None:
            return
        event = run.append(name, data)
        if name == "campaign":
            run.campaign = data
        if name in ("done", "error"):
            run.done = True
            run.finished_at = time.time()
            if name == "done" and isinstance(data.get("campaign"), dict):
                run.campaign = data["campaign"]

        loop = self._loop
        if loop is None:
            return
        for queue in list(run.subscribers):
            try:
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError:  # loop closed during shutdown
                pass

    def subscribe(self, run: Run) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        run.subscribers.add(queue)
        return queue

    def unsubscribe(self, run: Run, queue: asyncio.Queue) -> None:
        run.subscribers.discard(queue)


REGISTRY = Registry()
