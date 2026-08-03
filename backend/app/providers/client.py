"""TokenRouter client + startup model probe.

TokenRouter (tokenrouter.com) is an OpenAI-wire-compatible gateway. There is no
first-party Python SDK — their docs use plain `requests` and their FAQ points at
the OpenAI SDK. NOTE: the PyPI package named `tokenrouter` belongs to a
DIFFERENT company (tokenrouter.io); do not install it.

Model IDs need probing rather than trusting docs: TokenRouter's image docs use
"openai/gpt-5-image", but their live catalog lists that model under the chat
endpoint type, not image-generation. So we ask /v1/models what this key can
actually reach and pick the first candidate that is present.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from openai import OpenAI

from app.config import Resolved, get_settings

logger = logging.getLogger(__name__)

# Ordered by preference. Verified against TokenRouter's live pricing catalog as
# carrying supported_endpoint_types = ["image-generation"].
IMAGE_CANDIDATES = [
    "bytedance-seed/seedream-4.5",
    "bytedance-seed/seedream-5.0-pro",
    "bytedance-seed/seedream-5.0-lite",
    "openai/gpt-5.4-image-2",
]

# Vision + structured-output models, ordered by MEASURED behaviour against a
# live key (see scripts/probe_tokenrouter.py), not by documentation:
#   openai/gpt-5.4            vision OK, obeys json_schema exactly.  <-- winner
#   anthropic/claude-*        vision OK, but IGNORES the schema and invents its
#                             own keys, and rejects `temperature` outright.
#   google/gemini-3.5-flash   returns HTTP 200 with EMPTY content on multimodal
#                             requests, and never returns clean JSON. This is
#                             the dangerous one: it looks healthy and silently
#                             degrades every critique to the fallback verdict.
VISION_CANDIDATES = [
    "openai/gpt-5.4",
    "anthropic/claude-opus-5",
    "anthropic/claude-sonnet-5",
]

CHAT_CANDIDATES = [
    "openai/gpt-5.4",
    "anthropic/claude-opus-5",
    "anthropic/claude-sonnet-5",
]

# Text-only work: marketing copy, voiceover scripts, text critique, and every
# Campaign Brain lobe. Benchmarked on a real Campaign Brain prompt rather than
# chosen by reputation or price:
#   openai/gpt-5.4          9.8s, honoured the strict schema, no filler. <-- winner
#   openai/gpt-5.4-mini     5.6s and also clean; the faster fallback.
#   anthropic/claude-*     ~20s, correct but the slowest passing option, and it
#                           rejects `temperature` (see NO_TEMPERATURE_PREFIXES).
# Deliberately NOT here: google/gemini-3.5-flash returned unparseable JSON, and
# moonshotai/kimi-k3-free took over two minutes per call against an 8-per-minute
# cap — a five-lobe brain cannot run on that.
TEXT_CANDIDATES = [
    "openai/gpt-5.4",
    "openai/gpt-5.4-mini",
    "anthropic/claude-opus-5",
    "anthropic/claude-sonnet-5",
]

# Models that reject the `temperature` parameter outright with HTTP 400.
# anthropic/*: "`temperature` is deprecated for this model".
# moonshotai/*: "invalid temperature: only 1 is allowed for this model" —
# observed while benchmarking, and it fails EVERY call, so pinning
# FERNWOOD_TEXT_MODEL to a Kimi without this entry would 400 the whole text
# path rather than degrade.
NO_TEMPERATURE_PREFIXES = ("anthropic/", "moonshotai/")


@lru_cache(maxsize=1)
def tokenrouter_client() -> OpenAI:
    s = get_settings()
    if not s.has_tokenrouter:
        raise RuntimeError("TOKENROUTER_API_KEY is not set.")
    return OpenAI(
        api_key=s.tokenrouter_api_key,
        base_url=s.tokenrouter_base_url,
        timeout=120.0,
        max_retries=2,
    )


@lru_cache(maxsize=1)
def tokenrouter_chat_client() -> OpenAI:
    """Client for chat/LLM steps, with SDK retries capped at ONE.

    The default of 2 is too many here, because every chat call already sits
    under two retry layers we control: `_call_with_pacing` retries 429s with
    backoff, and the callers (brain/llm.py, pipeline/critique.py) each walk a
    response_format ladder on failure. Those compose multiplicatively — with
    SDK retries at 2 and a model that was merely slow rather than failing, one
    Campaign Brain lobe was measured occupying many minutes before reporting
    anything at all.

    One retry keeps genuine transient resilience (a dropped connection) without
    turning a slow response into a silent multi-minute stall.
    """
    s = get_settings()
    if not s.has_tokenrouter:
        raise RuntimeError("TOKENROUTER_API_KEY is not set.")
    return OpenAI(
        api_key=s.tokenrouter_api_key,
        base_url=s.tokenrouter_base_url,
        # Headroom over the per-request timeout so the deadline that fires is
        # the one the caller chose, with a message naming what it was doing.
        timeout=s.fernwood_text_request_timeout + 30.0,
        max_retries=1,
    )


def _available_model_ids() -> set[str]:
    try:
        page = tokenrouter_client().models.list()
        return {m.id for m in page.data}
    except Exception as exc:  # noqa: BLE001
        logger.warning("GET /v1/models failed (%s); falling back to defaults", exc)
        return set()


def _pick(candidates: list[str], available: set[str], override: str) -> tuple[str, str | None]:
    """Return (chosen_model, warning)."""
    if override.strip():
        return override.strip(), None
    if not available:
        return candidates[0], f"model list unavailable; defaulting to {candidates[0]}"
    for c in candidates:
        if c in available:
            return c, None
    return candidates[0], (
        f"none of {candidates} present in /v1/models; defaulting to {candidates[0]}"
    )


def _pick_text(available: set[str], configured: str) -> tuple[str, str | None]:
    """Resolve the text-only model, preferring the configured one.

    Unlike _pick(), a configured value is NOT taken on faith: FERNWOOD_TEXT_MODEL
    ships with a real default (the free Kimi tier), and a free tier can be
    withdrawn from the catalog at any time. So the configured id is treated as
    the head of the candidate list and still has to be present — otherwise a
    vanished free tier would 404 every copy, script and brain call at demo time.
    """
    configured = configured.strip()
    order = [configured, *TEXT_CANDIDATES] if configured else list(TEXT_CANDIDATES)
    if not available:
        return order[0], f"model list unavailable; defaulting text model to {order[0]}"
    for candidate in order:
        if candidate in available:
            warning = (
                None
                if candidate == order[0]
                else f"text model {order[0]} not in /v1/models; using {candidate}"
            )
            return candidate, warning
    return order[0], f"none of {order} present in /v1/models; defaulting to {order[0]}"


def _returns_usable_json(model: str) -> bool:
    """A model is only usable if it returns NON-EMPTY, parseable JSON.

    Checking HTTP 200 alone is not enough: google/gemini-3.5-flash answers 200
    with empty content on multimodal requests, which would silently degrade
    every critique to the heuristic fallback with no error anywhere.
    """
    import json as _json

    try:
        resp = tokenrouter_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Respond only with JSON."},
                {"role": "user", "content": 'Return exactly {"ok": true}.'},
            ],
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            return False
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return False
        return isinstance(_json.loads(text[start : end + 1]), dict)
    except Exception as exc:  # noqa: BLE001
        logger.debug("probe of %s failed: %s", model, exc)
        return False


def probe_models() -> None:
    """Resolve image/vision/chat models once at startup. Never raises."""
    s = get_settings()
    Resolved.warnings = []

    if not s.has_tokenrouter:
        Resolved.warnings.append("TOKENROUTER_API_KEY not set — generation will fail.")
        Resolved.image_model = s.fernwood_image_model or IMAGE_CANDIDATES[0]
        Resolved.vision_model = s.fernwood_vision_model or VISION_CANDIDATES[0]
        Resolved.chat_model = CHAT_CANDIDATES[0]
        Resolved.text_model = s.fernwood_text_model or TEXT_CANDIDATES[0]
        return

    available = _available_model_ids()

    Resolved.image_model, w1 = _pick(IMAGE_CANDIDATES, available, s.fernwood_image_model)
    Resolved.vision_model, w2 = _pick(VISION_CANDIDATES, available, s.fernwood_vision_model)
    Resolved.chat_model, w3 = _pick(CHAT_CANDIDATES, available, "")
    Resolved.text_model, w4 = _pick_text(available, s.fernwood_text_model)
    Resolved.warnings.extend(w for w in (w1, w2, w3, w4) if w)

    # Live-fire check of the resolved chat model. Cheap (one ~200 token call)
    # and it catches the silent-empty-response failure mode before a demo.
    if not s.fernwood_vision_model and not _returns_usable_json(Resolved.chat_model):
        for fallback in CHAT_CANDIDATES:
            if fallback != Resolved.chat_model and fallback in available:
                if _returns_usable_json(fallback):
                    Resolved.warnings.append(
                        f"{Resolved.chat_model} returned unusable output; "
                        f"switched to {fallback}."
                    )
                    Resolved.chat_model = fallback
                    Resolved.vision_model = fallback
                    break
        else:
            Resolved.warnings.append(
                f"{Resolved.chat_model} did not return usable JSON; "
                "critiques may degrade to heuristic verdicts."
            )

    # Live-fire the text model too. It carries copy, voiceover scripts, text
    # critique AND all five brain lobes, and it is a FREE tier — the failure
    # mode we actually have to survive is the free tier being throttled or
    # withdrawn on demo day, which a catalog listing alone will not reveal.
    if Resolved.text_model != Resolved.chat_model and not _returns_usable_json(
        Resolved.text_model
    ):
        Resolved.warnings.append(
            f"text model {Resolved.text_model} returned unusable output; "
            f"falling back to {Resolved.chat_model} for copy, scripts and the Campaign Brain."
        )
        Resolved.text_model = Resolved.chat_model

    if s.fernwood_tts_provider.lower() == "elevenlabs" and not s.has_elevenlabs:
        Resolved.warnings.append(
            "FERNWOOD_TTS_PROVIDER=elevenlabs but ELEVENLABS_API_KEY is unset."
        )

    logger.info(
        "Resolved models: image=%s vision=%s chat=%s text=%s (catalog=%d models)",
        Resolved.image_model,
        Resolved.vision_model,
        Resolved.chat_model,
        Resolved.text_model,
        len(available),
    )
