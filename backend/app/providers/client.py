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

# Vision-capable chat models. Gemini first: TokenRouter's routing table sends
# anthropic/* to /v1/messages and openai/gpt-5.4|5.5 to /v1/responses, which the
# OpenAI SDK's chat.completions path may not reach. Gemini image/flash models
# are listed as reachable over the OpenAI-compatible chat endpoint.
VISION_CANDIDATES = [
    "google/gemini-3.5-flash",
    "google/gemini-3.1-flash-image-preview",
    "anthropic/claude-sonnet-5",
    "anthropic/claude-opus-5",
]

CHAT_CANDIDATES = [
    "google/gemini-3.5-flash",
    "anthropic/claude-sonnet-5",
    "openai/gpt-5.4",
]


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


def probe_models() -> None:
    """Resolve image/vision/chat models once at startup. Never raises."""
    s = get_settings()
    Resolved.warnings = []

    if not s.has_tokenrouter:
        Resolved.warnings.append("TOKENROUTER_API_KEY not set — generation will fail.")
        Resolved.image_model = s.fernwood_image_model or IMAGE_CANDIDATES[0]
        Resolved.vision_model = s.fernwood_vision_model or VISION_CANDIDATES[0]
        Resolved.chat_model = CHAT_CANDIDATES[0]
        return

    available = _available_model_ids()

    Resolved.image_model, w1 = _pick(IMAGE_CANDIDATES, available, s.fernwood_image_model)
    Resolved.vision_model, w2 = _pick(VISION_CANDIDATES, available, s.fernwood_vision_model)
    Resolved.chat_model, w3 = _pick(CHAT_CANDIDATES, available, "")
    Resolved.warnings.extend(w for w in (w1, w2, w3) if w)

    if not s.has_elevenlabs and s.fernwood_enable_tts:
        Resolved.warnings.append("ELEVENLABS_API_KEY not set — audio track will degrade.")

    logger.info(
        "Resolved models: image=%s vision=%s chat=%s (catalog=%d models)",
        Resolved.image_model,
        Resolved.vision_model,
        Resolved.chat_model,
        len(available),
    )
