"""TokenRouterTTSProvider — speech synthesis through TokenRouter.

WHY THIS EXISTS: ElevenLabs' free tier is 10,000 characters/month, which a few
campaigns exhaust (observed: 9,983/10,000, resetting ~29 days out). Once
exhausted every TTS call returns auth_failure and the audio track dies.

TokenRouter has no dedicated /v1/audio/speech route — `tts-1` and
`gpt-4o-mini-tts` both return 503 model_not_found. But `openai/gpt-audio-mini`
is registered with endpoint type `audio-chat`, which is OpenAI's
audio-out-over-chat shape:

    POST /v1/chat/completions
    { "modalities": ["text","audio"], "audio": {"voice": ..., "format": "mp3"} }
    -> choices[0].message.audio.data  (base64 mp3)

Verified live: returns a valid 24 kHz mono MP3 that transcribes back verbatim.

NOTE: `openai/gpt-audio` (the non-mini model) rejects this with "Audio output
requires stream: true", so the mini model is the one to use for a simple
non-streaming call.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any

import httpx
from genblaze_core.exceptions import ProviderError
from genblaze_core.models.asset import Asset
from genblaze_core.models.enums import ProviderErrorCode
from genblaze_core.models.step import Step
from genblaze_core.providers import SyncProvider

from app.config import SCRATCH_DIR
from app.providers.tokenrouter_image import _classify, _err_msg

logger = logging.getLogger(__name__)

# OpenAI's voice set, exposed through TokenRouter.
VOICES = ("alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse")


class TokenRouterTTSProvider(SyncProvider):
    """Synchronous TTS via TokenRouter's audio-chat models."""

    name = "tokenrouter-tts"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        request_timeout: float = 240.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._api_key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = request_timeout

    def generate(self, step: Step, config: Any = None) -> Step:
        params = step.params or {}
        voice = params.get("voice", "ash")
        script = (step.prompt or "").strip()
        if not script:
            raise ProviderError(
                "No script supplied for TTS", error_code=ProviderErrorCode.INVALID_INPUT
            )

        payload = {
            "model": step.model,
            "modalities": ["text", "audio"],
            "audio": {"voice": voice, "format": params.get("format", "mp3")},
            "messages": [
                {
                    "role": "user",
                    # The model is a chat model, so it needs telling that this is
                    # narration to read rather than a prompt to answer.
                    "content": (
                        "Read the following brand voiceover script aloud exactly as "
                        "written. Do not add, omit, summarise or comment on anything. "
                        f"Delivery: {params.get('delivery', 'warm, unhurried, natural')}.\n\n"
                        f"{script}"
                    ),
                }
            ],
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    f"{self._base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"TokenRouter TTS timed out after {self._timeout}s",
                error_code=ProviderErrorCode.TIMEOUT,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"TokenRouter TTS transport error: {exc}",
                error_code=ProviderErrorCode.SERVER_ERROR,
            ) from exc

        if resp.status_code >= 400:
            raise ProviderError(
                f"TokenRouter TTS {resp.status_code} on {step.model}: {_err_msg(resp)}",
                error_code=_classify(resp.status_code),
            )

        raw = self._extract_audio(resp.json())

        SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
        out = SCRATCH_DIR / f"{step.step_id}.mp3"
        out.write_bytes(raw)

        asset = Asset(
            url=out.resolve().as_uri(),
            media_type="audio/mpeg",
            sha256=hashlib.sha256(raw).hexdigest(),
            size_bytes=len(raw),
        )
        asset.metadata.update({"voice": voice, "upstream_model": step.model})
        try:
            from mutagen.mp3 import MP3

            asset.duration = round(MP3(str(out)).info.length, 2)
        except Exception:  # noqa: BLE001 - duration is nice-to-have
            pass

        step.assets.append(asset)
        step.metadata["local_path"] = str(out)
        step.metadata["voice"] = voice
        return step

    @staticmethod
    def _extract_audio(body: dict[str, Any]) -> bytes:
        """Pull base64 audio out of the chat response, tolerating shape drift."""
        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                f"Unexpected TTS response; keys={sorted(body)[:10]}",
                error_code=ProviderErrorCode.UNKNOWN,
            ) from exc

        audio = message.get("audio") or {}
        data = audio.get("data") if isinstance(audio, dict) else None
        if not data:
            # Some gateways inline it as a content part instead.
            content = message.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        candidate = (part.get("input_audio") or part.get("audio") or {})
                        if isinstance(candidate, dict) and candidate.get("data"):
                            data = candidate["data"]
                            break
        if not data:
            raise ProviderError(
                "TTS response contained no audio payload — the model may have "
                "replied with text only",
                error_code=ProviderErrorCode.UNKNOWN,
            )

        try:
            return base64.b64decode(data, validate=False)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                "Malformed base64 audio from TokenRouter",
                error_code=ProviderErrorCode.UNKNOWN,
            ) from exc
