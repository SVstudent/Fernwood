"""DeepgramTTSProvider — Aura TTS, plus a Deepgram STT helper.

Deepgram replaces ElevenLabs as the fallback voiceover backend. ElevenLabs' free
tier is 10,000 characters/month and returns auth_failure once spent, which
killed the audio track mid-run; Deepgram's batch REST TTS is a single
synchronous call with no such cliff here.

    POST https://api.deepgram.com/v1/speak?model=<voice>&encoding=mp3
    Authorization: Token <key>
    {"text": "..."}                      -> audio/mpeg bytes directly

Verified live: aura-2-thalia-en / aura-2-andromeda-en / aura-asteria-en all
return 24 kHz mono MP3.

The module also exposes `transcribe()` (Deepgram STT, nova-3). That is used by
the audio verification tests: a purpose-built STT engine returns the words and
nothing else, where an audio-capable *chat* model prepends commentary like
"Here it is, verbatim:" and mis-hears proper nouns — which made those tests
flaky.
"""

from __future__ import annotations

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

logger = logging.getLogger(__name__)

API = "https://api.deepgram.com/v1"

# A few Aura voices, verified reachable. aura-2-* is the current generation.
VOICES = (
    "aura-2-thalia-en",
    "aura-2-andromeda-en",
    "aura-2-apollo-en",
    "aura-2-arcas-en",
    "aura-asteria-en",
)


def _classify(status: int) -> ProviderErrorCode:
    if status in (401, 403):
        return ProviderErrorCode.AUTH_FAILURE
    if status == 404:
        return ProviderErrorCode.MODEL_ERROR
    if status == 429:
        return ProviderErrorCode.RATE_LIMIT
    if status in (408, 504):
        return ProviderErrorCode.TIMEOUT
    if status == 400:
        return ProviderErrorCode.INVALID_INPUT
    if status >= 500:
        return ProviderErrorCode.SERVER_ERROR
    return ProviderErrorCode.UNKNOWN


class DeepgramTTSProvider(SyncProvider):
    """Synchronous TTS via Deepgram Aura (batch REST)."""

    name = "deepgram-tts"

    def __init__(
        self,
        api_key: str,
        *,
        request_timeout: float = 180.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._api_key = api_key
        self._timeout = request_timeout

    def generate(self, step: Step, config: Any = None) -> Step:
        script = (step.prompt or "").strip()
        if not script:
            raise ProviderError(
                "No script supplied for TTS",
                error_code=ProviderErrorCode.INVALID_INPUT,
            )

        params = step.params or {}
        # step.model carries the Aura voice id (Deepgram's "model" IS the voice).
        voice = step.model or params.get("voice") or VOICES[0]
        encoding = params.get("encoding", "mp3")

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    f"{API}/speak",
                    params={"model": voice, "encoding": encoding},
                    headers={
                        "Authorization": f"Token {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"text": script},
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"Deepgram TTS timed out after {self._timeout}s",
                error_code=ProviderErrorCode.TIMEOUT,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Deepgram TTS transport error: {exc}",
                error_code=ProviderErrorCode.SERVER_ERROR,
            ) from exc

        if resp.status_code >= 400:
            raise ProviderError(
                f"Deepgram TTS {resp.status_code} on {voice}: {resp.text[:200]}",
                error_code=_classify(resp.status_code),
            )

        raw = resp.content
        if not raw or len(raw) < 512:
            raise ProviderError(
                f"Deepgram returned {len(raw)} bytes — not usable audio",
                error_code=ProviderErrorCode.UNKNOWN,
            )

        SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
        suffix = ".mp3" if encoding == "mp3" else ".wav"
        out = SCRATCH_DIR / f"{step.step_id}{suffix}"
        out.write_bytes(raw)

        asset = Asset(
            url=out.resolve().as_uri(),
            media_type="audio/mpeg" if encoding == "mp3" else "audio/wav",
            sha256=hashlib.sha256(raw).hexdigest(),
            size_bytes=len(raw),
        )
        asset.metadata.update({"voice": voice, "provider": "deepgram"})
        try:
            from mutagen.mp3 import MP3

            if suffix == ".mp3":
                asset.duration = round(MP3(str(out)).info.length, 2)
        except Exception:  # noqa: BLE001
            pass

        step.assets.append(asset)
        step.metadata["local_path"] = str(out)
        step.metadata["voice"] = voice
        return step


def transcribe(audio: bytes, api_key: str, *, model: str = "nova-3") -> tuple[str, float]:
    """Deepgram STT. Returns (transcript, confidence).

    Purpose-built ASR, so the output is the spoken words and nothing else —
    unlike an audio chat model, which editorialises and mis-hears proper nouns.
    """
    resp = httpx.post(
        f"{API}/listen",
        params={"model": model, "smart_format": "true"},
        headers={"Authorization": f"Token {api_key}", "Content-Type": "audio/mpeg"},
        content=audio,
        timeout=180,
    )
    if resp.status_code >= 400:
        raise ProviderError(
            f"Deepgram STT {resp.status_code}: {resp.text[:200]}",
            error_code=_classify(resp.status_code),
        )
    alt = resp.json()["results"]["channels"][0]["alternatives"][0]
    return alt.get("transcript", ""), float(alt.get("confidence", 0.0))
