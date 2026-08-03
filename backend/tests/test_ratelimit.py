"""Free-tier request pacing.

These exist because the failure they prevent is silent: an unpaced run does not
crash, it just quietly loses every Campaign Brain lobe to 429s and ships a
campaign with heuristic critiques. Tests use a short window so they stay fast
while exercising the real clock path.
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from app.providers.ratelimit import SlidingWindowLimiter, is_free_tier, limiter_for, reset


def _step(model: str):
    """Minimal stand-in for a genblaze Step.

    The real Step requires a bound provider, which would drag the whole
    Pipeline machinery into a test about pacing. _call_with_pacing reads only
    .model and .prompt.
    """
    return SimpleNamespace(step_id="s", model=model, prompt="hi")


@pytest.fixture(autouse=True)
def clean_registry():
    reset()
    yield
    reset()


def test_free_tier_detection_matches_vendor_naming():
    """Matched by convention so a new free model is paced without a code change."""
    assert is_free_tier("moonshotai/kimi-k3-free")
    assert is_free_tier("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
    assert not is_free_tier("moonshotai/kimi-k3")
    assert not is_free_tier("openai/gpt-5.4")
    assert not is_free_tier("bytedance-seed/seedream-4.5")


def test_calls_within_the_limit_are_not_delayed():
    limiter = SlidingWindowLimiter(max_calls=3, period=60.0)
    start = time.monotonic()
    for _ in range(3):
        assert limiter.acquire() == 0.0
    assert time.monotonic() - start < 0.2


def test_the_call_over_the_limit_blocks_until_the_window_slides():
    limiter = SlidingWindowLimiter(max_calls=2, period=1.0)
    limiter.acquire()
    limiter.acquire()

    start = time.monotonic()
    waited = limiter.acquire()
    elapsed = time.monotonic() - start

    # Must actually wait out the window rather than passing straight through.
    assert waited > 0
    assert elapsed >= 1.0


def test_note_rejection_spends_the_whole_window():
    """A 429 means the server disagrees with our count, so trust the server."""
    limiter = SlidingWindowLimiter(max_calls=4, period=1.0)
    limiter.note_rejection()

    start = time.monotonic()
    limiter.acquire()
    assert time.monotonic() - start >= 1.0


def test_limiter_is_shared_per_model_and_rebuilt_when_the_cap_changes():
    first = limiter_for("moonshotai/kimi-k3-free", 7)
    assert limiter_for("moonshotai/kimi-k3-free", 7) is first
    assert limiter_for("openai/gpt-5.4", 7) is not first
    # A changed cap must produce a limiter that honours it, not a stale one.
    assert limiter_for("moonshotai/kimi-k3-free", 3).max_calls == 3


def test_limiter_is_thread_safe_under_contention():
    """The pipeline paces from a worker thread while SSE serves the event loop."""
    limiter = SlidingWindowLimiter(max_calls=20, period=60.0)
    errors: list[Exception] = []

    def worker():
        try:
            for _ in range(5):
                limiter.acquire()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    # Exactly 20 slots were handed out, with no double-issue and none lost.
    assert len(limiter._calls) == 20


def test_chat_step_paces_free_models_and_leaves_others_alone(monkeypatch):
    """The seam every text call goes through — copy, critique and all five lobes."""
    from app.providers import tokenrouter_chat

    acquired: list[str] = []

    class FakeLimiter:
        max_calls = 7

        def acquire(self):
            acquired.append("paced")
            return 0.0

        def note_rejection(self):
            pass

    monkeypatch.setattr(
        tokenrouter_chat, "chat", lambda *a, **k: type("R", (), {"text": "{}"})()
    )
    monkeypatch.setattr(
        "app.providers.ratelimit.limiter_for", lambda model, cap, period=60.0: FakeLimiter()
    )

    free_step = _step("moonshotai/kimi-k3-free")
    tokenrouter_chat._call_with_pacing(free_step, None, {})
    assert acquired == ["paced"]

    paid_step = _step("openai/gpt-5.4")
    tokenrouter_chat._call_with_pacing(paid_step, None, {})
    assert acquired == ["paced"]  # unchanged — paid models are not throttled


def test_chat_step_retries_a_rate_limited_free_model(monkeypatch):
    """A stray 429 must not reach the caller's response_format ladder."""
    from app.providers import tokenrouter_chat

    calls = {"n": 0}
    rejections = {"n": 0}

    class FakeLimiter:
        max_calls = 7

        def acquire(self):
            return 0.0

        def note_rejection(self):
            rejections["n"] += 1

    def flaky_chat(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Error code: 429 - You have reached the request limit")
        return type("R", (), {"text": '{"ok": true}'})()

    monkeypatch.setattr(tokenrouter_chat, "chat", flaky_chat)
    monkeypatch.setattr(
        "app.providers.ratelimit.limiter_for", lambda model, cap, period=60.0: FakeLimiter()
    )

    result = tokenrouter_chat._call_with_pacing(_step("moonshotai/kimi-k3-free"), None, {})

    assert result.text == '{"ok": true}'
    assert calls["n"] == 2
    assert rejections["n"] == 1


def test_brain_lobe_abandons_the_ladder_on_a_persistent_rate_limit(monkeypatch):
    """Walking the ladder on a 429 spends slots the upstream has already refused."""
    from app.brain import llm

    attempts: list[object] = []

    def always_rate_limited(*args, **kwargs):
        attempts.append(kwargs.get("response_format"))
        raise RuntimeError("Error code: 429 - request limit reached")

    monkeypatch.setattr(llm, "make_sink", lambda cid: None)

    class FakePipeline:
        def __init__(self, *a, **k):
            pass

        def step(self, *a, **k):
            always_rate_limited(**k.get("params", {}))
            return self

        def run(self, **k):
            raise AssertionError("unreachable")

    monkeypatch.setattr(llm, "Pipeline", FakePipeline)

    parsed, manifest = llm.brain_call(
        "strategy", campaign_id="c", prompt="p", schema={"type": "json_object"}
    )

    assert parsed is None and manifest is None
    # Stopped after the FIRST rejection instead of burning all three formats.
    assert len(attempts) == 1
