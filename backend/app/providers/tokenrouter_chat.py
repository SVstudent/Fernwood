"""TokenRouterChatStep — wraps a genblaze chat() call as a real Pipeline step.

WHY THIS EXISTS: genblaze's chat() helper is explicitly outside the
Pipeline/Provider machinery and produces no Manifest. docs/features/llm-calls.md
gives the sanctioned recipe for getting provenance anyway — wrap the call in a
SyncProvider — which is better than hand-constructing Manifest records, because
copy and critique then flow through the SAME sink and manifest path as the image
and audio steps. One provenance code path instead of two.

DEVIATION FROM THE DOC'S RECIPE (important): the doc emits
    Asset(url=f"text:{digest}", ...)
That works only when no sink is attached. With a sink, ObjectStorageSink's
AssetTransfer dispatches on scheme — _LOCAL_SCHEMES is exactly {"file"}, so a
`text:` URL falls through to the HTTP download branch and raises, which fails
write_run() and skips the manifest upload entirely. So we write the response to
a temp .json file and emit file:// with media_type="application/json".
The text is still carried in metadata["text"], which is what genblaze's own
moderation code reads for textual assets.

ROUTING: chat() picks its provider by import module and has no provider= param.
We import from genblaze_openai and hand it a `client=` pointed at TokenRouter —
so nothing reaches OpenAI, only the wire format is borrowed.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from genblaze_core.exceptions import ProviderError
from genblaze_core.models.asset import Asset
from genblaze_core.models.enums import ProviderErrorCode
from genblaze_core.models.step import Step
from genblaze_core.providers import SyncProvider
from genblaze_openai import chat

from app.config import SCRATCH_DIR, get_settings
from app.providers.client import NO_TEMPERATURE_PREFIXES, tokenrouter_chat_client

logger = logging.getLogger(__name__)


class TokenRouterChatStep(SyncProvider):
    """A chat/LLM call recorded as a first-class Genblaze step.

    Step params consumed:
      messages          list[dict]  full message list (takes precedence)
      system            str         system prompt (used with step.prompt)
      response_format   dict        passed straight through to chat()
      temperature       float
      max_tokens        int
      request_timeout   float
    """

    name = "tokenrouter-chat"

    def generate(self, step: Step, config: Any = None) -> Step:
        params = step.params or {}
        messages = params.get("messages")

        kwargs: dict[str, Any] = {
            # Retry-free client: our pacing layer and the caller's
            # response_format ladder are the retry policy. See
            # tokenrouter_chat_client() for why SDK retries are actively harmful
            # on a slow, rate-limited free tier.
            "client": tokenrouter_chat_client(),
            # Default comes from settings, not a literal: the free text tier is
            # slow enough that a 90s default silently failed copy generation,
            # text critique and the brain lobes in three different-looking ways.
            "timeout": params.get("request_timeout")
            or get_settings().fernwood_text_request_timeout,
        }
        for key in ("temperature", "max_tokens", "response_format"):
            if params.get(key) is not None:
                kwargs[key] = params[key]

        # Some upstreams reject `temperature` outright ("`temperature` is
        # deprecated for this model" -> HTTP 400). Verified on anthropic/*.
        if step.model.startswith(NO_TEMPERATURE_PREFIXES):
            kwargs.pop("temperature", None)
        if not messages and params.get("system"):
            kwargs["system"] = params["system"]

        try:
            resp = _call_with_pacing(step, messages, kwargs)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                f"TokenRouter chat failed on {step.model}: {exc}",
                error_code=_classify_chat_error(exc),
            ) from exc

        text = resp.text or ""
        payload = json.dumps(
            {
                "model": resp.model,
                "text": text,
                "finish_reason": resp.finish_reason,
                "tokens_in": resp.tokens_in,
                "tokens_out": resp.tokens_out,
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")

        SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
        out = SCRATCH_DIR / f"{step.step_id}.json"
        out.write_bytes(payload)

        asset = Asset(
            url=out.resolve().as_uri(),
            media_type="application/json",
            sha256=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
            # metadata["text"] is what Pipeline's moderation hook reads for
            # textual assets, and how downstream steps recover the content.
            metadata={"text": text},
        )
        step.assets.append(asset)
        step.metadata["tokens_out"] = resp.tokens_out or 0
        step.metadata["local_path"] = str(out)
        return step


def _is_rate_limit(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "request limit" in text


def _call_with_pacing(step: Step, messages: Any, kwargs: dict[str, Any]) -> Any:
    """Send the request, paced under any free-tier request cap.

    Free models (kimi-k3-free allows 8/min) are throttled BEFORE sending. The
    retry loop is the backstop for the pacing being slightly out of phase with
    the server's own window — without it, a single stray 429 would collapse the
    caller's response_format ladder, since a rejected request is indistinguishable
    from a malformed response to the layer above.
    """
    from app.config import get_settings
    from app.providers.ratelimit import is_free_tier, limiter_for

    settings = get_settings()
    limiter = (
        limiter_for(step.model, settings.fernwood_free_tier_rpm)
        if is_free_tier(step.model)
        else None
    )

    attempts = max(1, settings.fernwood_rate_limit_retries) if limiter else 1
    last: Exception | None = None

    for attempt in range(attempts):
        if limiter is not None:
            limiter.acquire()
        try:
            if messages:
                return chat(step.model, messages, **kwargs)
            return chat(step.model, prompt=step.prompt or "", **kwargs)
        except Exception as exc:  # noqa: BLE001
            if limiter is None or not _is_rate_limit(exc) or attempt == attempts - 1:
                raise
            last = exc
            # The upstream has already refused, so treat the window as spent
            # rather than trusting our own count of it.
            limiter.note_rejection()
            logger.warning(
                "rate limited on %s (attempt %d/%d); backing off",
                step.model,
                attempt + 1,
                attempts,
            )

    raise last or RuntimeError("unreachable")


def _classify_chat_error(exc: Exception) -> ProviderErrorCode:
    text = str(exc).lower()
    if "rate limit" in text or "429" in text:
        return ProviderErrorCode.RATE_LIMIT
    if "timeout" in text or "timed out" in text:
        return ProviderErrorCode.TIMEOUT
    if "401" in text or "invalid token" in text or "unauthor" in text:
        return ProviderErrorCode.AUTH_FAILURE
    if "404" in text or "not found" in text or "invalid url" in text:
        return ProviderErrorCode.MODEL_ERROR
    return ProviderErrorCode.UNKNOWN


def step_text(step: Step) -> str:
    """Recover the model's text from a completed TokenRouterChatStep step."""
    for asset in step.assets:
        text = (asset.metadata or {}).get("text")
        if text:
            return str(text)
    return ""
