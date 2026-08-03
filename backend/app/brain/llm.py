"""One inference helper shared by all five lobes.

Every lobe call is a real Genblaze Pipeline step, not a bare chat() — so the
brain's own reasoning lands in B2 with a SHA-256 manifest, exactly like the
image and copy it directs. "The brain is auditable too" is not a slogan here;
each lobe's manifest hash is recorded on the campaign.

Two invariants this module exists to enforce:

  1. NEVER RAISE. A lobe that fails returns (None, None) and the caller marks
     that lobe 'skipped'. The Campaign Brain is a multiplier on the pipeline,
     never a new way for the pipeline to die.
  2. DEGRADE THE RESPONSE FORMAT, NOT THE RUN. Strict json_schema first, then
     json_object, then free text scraped for JSON — the same ladder
     app/pipeline/critique.py uses, for the same reason: a stray backtick must
     not cost a demo.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from genblaze_core import Modality, Pipeline

from app.config import Resolved
from app.pipeline.schemas import loads_lenient
from app.providers.tokenrouter_chat import TokenRouterChatStep, step_text
from app.storage.factory import make_sink

logger = logging.getLogger(__name__)

BRAIN_SYSTEM = (
    "You are the Campaign Brain: the accumulated brand intelligence behind an "
    "automated creative studio. You are precise, commercially literate and "
    "allergic to marketing platitudes. You never invent evidence you were not "
    "given. Respond only with JSON matching the requested schema."
)

# Generous on purpose. Kimi truncated a Foresight response mid-string at 700
# tokens, which produces unparseable JSON and silently skips the lobe — a
# failure mode that looks identical to the model being unavailable. Structured
# output must never be cut off, and finishing early costs nothing.
_MAX_TOKENS = 2400

# Wall-clock ceiling for ONE lobe across its whole response_format ladder.
# The resolved model answers a lobe in ~10s, so this is roughly 18x headroom —
# it exists to bound the pathological case, not the normal one. Without it, a
# model that goes slow rather than failing walks all three ladder rungs back to
# back and holds the campaign for minutes before reporting that it gave up.
# Better a skipped lobe than a stalled demo: the pipeline is the product.
_LOBE_BUDGET_SECONDS = 180.0


def brain_call(
    lobe: str,
    *,
    campaign_id: str,
    prompt: str,
    schema: dict[str, Any],
    max_tokens: int = _MAX_TOKENS,
    temperature: float = 0.7,
) -> tuple[dict[str, Any] | None, str | None]:
    """Run one lobe. Returns (parsed_json, manifest_hash) — never raises.

    `campaign_id` doubles as the Genblaze project_id, so brain manifests land
    under the same campaign tree as the assets they shaped.
    """
    deadline = time.monotonic() + _LOBE_BUDGET_SECONDS

    for response_format in (schema, {"type": "json_object"}, None):
        if time.monotonic() > deadline:
            logger.warning("brain lobe %s exceeded its time budget; skipping", lobe)
            return None, None
        try:
            result = (
                Pipeline(
                    f"{campaign_id}-brain-{lobe}",
                    tenant_id="fernwood",
                    project_id=campaign_id,
                    preflight=False,  # TokenRouter slugs are in no ModelRegistry
                )
                .step(
                    TokenRouterChatStep(),
                    model=Resolved.text_model,
                    prompt=prompt,
                    modality=Modality.TEXT,
                    metadata={
                        "campaign_id": campaign_id,
                        "role": "campaign_brain",
                        "lobe": lobe,
                    },
                    params={
                        "messages": [
                            {"role": "system", "content": BRAIN_SYSTEM},
                            {"role": "user", "content": prompt},
                        ],
                        "response_format": response_format,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                .run(sink=make_sink(campaign_id), timeout=180, raise_on_failure=True)
            )
            parsed = loads_lenient(step_text(result.run.steps[0]))
            if parsed:
                return parsed, result.manifest.canonical_hash
            logger.warning("brain lobe %s returned unparseable JSON (rf=%s)", lobe, response_format)
        except Exception as exc:  # noqa: BLE001 - try the next, looser format
            logger.warning("brain lobe %s failed (rf=%s): %s", lobe, response_format, str(exc)[:200])
            # A rate-limited request is NOT a schema problem, and the provider
            # already retried with backoff before surfacing it. Walking the rest
            # of the ladder would spend two more slots in a window the upstream
            # has already closed, and starve the lobes queued behind this one.
            if _rate_limited(exc):
                logger.warning("brain lobe %s abandoned: upstream rate limit", lobe)
                return None, None
            continue

    logger.warning("brain lobe %s exhausted all response formats; skipping", lobe)
    return None, None


def _rate_limited(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "request limit" in text


def clamp(value: Any, lo: int = 0, hi: int = 100, default: int = 0) -> int:
    """Coerce a model-supplied number into range. Models return 0.87 for 87."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    if 0.0 < num <= 1.0 and hi > 1:
        num *= 100
    return max(lo, min(hi, int(round(num))))
