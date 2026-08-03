"""Client-side rate limiting for free-tier models.

WHY THIS EXISTS: `moonshotai/kimi-k3-free` enforces **8 requests per minute**
and returns HTTP 429 the instant you exceed it. Discovered live, and it is
brutal in exactly the wrong place — one campaign makes ~20 text calls (copy,
voiceover script, both text critiques, their retries, and five Campaign Brain
lobes), so an unthrottled run trips the limit within the first thirty seconds
and every lobe after that degrades to 'skipped'.

Worse, the degradation ladders in brain/llm.py and pipeline/critique.py made it
self-amplifying: a 429 looks like a bad response, so the caller immediately
retried with a looser response_format, which was also 429, which burned the
whole ladder in under three seconds and produced a heuristic verdict.

So requests are paced BEFORE they are sent rather than repaired afterwards. A
sliding window is used rather than a token bucket because the upstream limit is
itself a sliding window ("maximum 8 requests within 1 minute") — a bucket that
refills smoothly would still permit a burst that the server counts as over
limit.

Only models the caller marks as rate-limited are paced; everything else calls
straight through with no lock and no measurable overhead.
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)


class SlidingWindowLimiter:
    """Blocks until a call fits inside `max_calls` per `period` seconds.

    Thread-safe: the pipeline runs in a worker thread while FastAPI serves the
    SSE stream on the event loop, and a future parallel track would share this
    limiter across threads.
    """

    def __init__(self, max_calls: int, period: float = 60.0) -> None:
        self.max_calls = max(1, max_calls)
        self.period = period
        self._calls: list[float] = []
        self._lock = threading.Lock()

    def acquire(self) -> float:
        """Reserve a slot, sleeping if necessary. Returns seconds waited."""
        waited = 0.0
        while True:
            with self._lock:
                now = time.monotonic()
                # Drop everything that has aged out of the window.
                cutoff = now - self.period
                self._calls = [t for t in self._calls if t > cutoff]

                if len(self._calls) < self.max_calls:
                    self._calls.append(now)
                    return waited

                # Wait for the oldest call to leave the window. The margin
                # matters: the server's clock is not ours, and sleeping until
                # the exact boundary reliably lands one request too early.
                sleep_for = (self._calls[0] + self.period) - now + 0.35

            logger.info(
                "rate limit: pacing request, sleeping %.1fs (%d/%d in window)",
                sleep_for,
                len(self._calls),
                self.max_calls,
            )
            time.sleep(max(0.1, sleep_for))
            waited += max(0.1, sleep_for)

    def note_rejection(self) -> None:
        """Record a 429 the pacing failed to prevent.

        Fills the window so the next acquire() waits out a full period instead
        of hammering an upstream that has already said no.
        """
        with self._lock:
            now = time.monotonic()
            self._calls = [now] * self.max_calls


_limiters: dict[str, SlidingWindowLimiter] = {}
_registry_lock = threading.Lock()


def is_free_tier(model: str) -> bool:
    """Heuristic for models that carry a hard free-tier request cap.

    Matches the vendor naming convention rather than a hardcoded allow-list
    ("moonshotai/kimi-k3-free", "nvidia/...:free"), so a future free model is
    paced automatically instead of taking down a demo before anyone notices it
    needed adding.
    """
    lowered = model.lower()
    return lowered.endswith("-free") or lowered.endswith(":free") or "-free-" in lowered


def limiter_for(model: str, max_calls: int, period: float = 60.0) -> SlidingWindowLimiter:
    """Process-wide limiter for one model id."""
    with _registry_lock:
        limiter = _limiters.get(model)
        if limiter is None or limiter.max_calls != max_calls:
            limiter = SlidingWindowLimiter(max_calls, period)
            _limiters[model] = limiter
        return limiter


def reset() -> None:
    """Drop all limiters. Test-support only."""
    with _registry_lock:
        _limiters.clear()
