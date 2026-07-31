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

from app.config import SCRATCH_DIR
from app.providers.client import tokenrouter_client

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
            "client": tokenrouter_client(),
            "timeout": params.get("request_timeout", 90.0),
        }
        for key in ("temperature", "max_tokens", "response_format"):
            if params.get(key) is not None:
                kwargs[key] = params[key]
        if not messages and params.get("system"):
            kwargs["system"] = params["system"]

        try:
            if messages:
                resp = chat(step.model, messages, **kwargs)
            else:
                resp = chat(step.model, prompt=step.prompt or "", **kwargs)
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
