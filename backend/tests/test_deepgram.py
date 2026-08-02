"""Deepgram TTS provider and its place in the voiceover fallback chain."""

from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
import pytest
from genblaze_core.exceptions import ProviderError
from genblaze_core.models.enums import ProviderErrorCode
from genblaze_core.models.step import Step

from app.providers.deepgram_tts import VOICES, DeepgramTTSProvider, transcribe

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" + b"\x00" * 4096


@pytest.fixture
def provider():
    return DeepgramTTSProvider(api_key="dg_key")


def _step(model="aura-2-thalia-en", prompt="At Fernwood Goods.", **params) -> Step:
    return Step(provider="deepgram-tts", model=model, prompt=prompt, params=params)


class TestRequestShape:
    def test_posts_text_to_speak_endpoint(self, provider, monkeypatch):
        seen = {}

        def fake_post(self, url, params=None, headers=None, json=None):
            seen.update({"url": url, "params": params, "headers": headers, "json": json})
            return httpx.Response(200, content=MP3, headers={"content-type": "audio/mpeg"})

        monkeypatch.setattr(httpx.Client, "post", fake_post)
        provider.generate(_step())

        assert seen["url"].endswith("/v1/speak")
        assert seen["json"] == {"text": "At Fernwood Goods."}
        assert seen["headers"]["Authorization"] == "Token dg_key"

    def test_model_is_the_voice(self, provider, monkeypatch):
        """Deepgram has no separate voice param — the model IS the voice."""
        seen = {}
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, params=None, headers=None, json=None: (
                seen.update(params or {}),
                httpx.Response(200, content=MP3),
            )[1],
        )
        provider.generate(_step(model="aura-2-andromeda-en"))
        assert seen["model"] == "aura-2-andromeda-en"
        assert seen["encoding"] == "mp3"

    def test_empty_script_rejected(self, provider):
        with pytest.raises(ProviderError) as exc:
            provider.generate(_step(prompt="  "))
        assert exc.value.error_code == ProviderErrorCode.INVALID_INPUT

    def test_known_voices_listed(self):
        assert "aura-2-thalia-en" in VOICES


class TestResponseHandling:
    def _wire(self, monkeypatch, status=200, content=MP3):
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, params=None, headers=None, json=None: httpx.Response(
                status, content=content, headers={"content-type": "audio/mpeg"}
            ),
        )

    def test_emits_hashed_file_asset(self, provider, monkeypatch):
        self._wire(monkeypatch)
        step = _step()
        out = provider.generate(step)
        asset = out.assets[0]
        assert asset.media_type == "audio/mpeg"
        assert asset.size_bytes == len(MP3)
        assert len(asset.sha256) == 64
        assert asset.metadata["provider"] == "deepgram"

    def test_asset_written_under_system_temp(self, provider, monkeypatch):
        """ObjectStorageSink only reads file:// assets from gettempdir()."""
        self._wire(monkeypatch)
        step = _step()
        provider.generate(step)
        path = Path(step.metadata["local_path"]).resolve()
        assert path.is_relative_to(Path(tempfile.gettempdir()).resolve())

    def test_truncated_response_rejected(self, provider, monkeypatch):
        """A few bytes is an error page, not audio."""
        self._wire(monkeypatch, content=b"nope")
        with pytest.raises(ProviderError, match="not usable audio"):
            provider.generate(_step())

    @pytest.mark.parametrize(
        "status,code",
        [
            (401, ProviderErrorCode.AUTH_FAILURE),
            (429, ProviderErrorCode.RATE_LIMIT),
            (400, ProviderErrorCode.INVALID_INPUT),
            (503, ProviderErrorCode.SERVER_ERROR),
        ],
    )
    def test_errors_classified(self, provider, monkeypatch, status, code):
        self._wire(monkeypatch, status=status, content=b'{"err":"x"}')
        with pytest.raises(ProviderError) as exc:
            provider.generate(_step())
        assert exc.value.error_code == code


class TestTranscribeHelper:
    def test_returns_transcript_and_confidence(self, monkeypatch):
        monkeypatch.setattr(
            httpx,
            "post",
            lambda *a, **k: httpx.Response(
                200,
                json={
                    "results": {
                        "channels": [
                            {"alternatives": [{"transcript": "hello there", "confidence": 0.99}]}
                        ]
                    }
                },
            ),
        )
        text, conf = transcribe(MP3, "dg_key")
        assert text == "hello there"
        assert conf == pytest.approx(0.99)

    def test_error_raises_provider_error(self, monkeypatch):
        monkeypatch.setattr(
            httpx, "post", lambda *a, **k: httpx.Response(401, content=b"bad key")
        )
        with pytest.raises(ProviderError):
            transcribe(MP3, "dg_key")


class TestFallbackChain:
    """A vendor quota must never cost the campaign its voiceover."""

    def _patch(self, monkeypatch, ok: set[str]):
        calls: list[str] = []
        from app.pipeline import tracks

        def make(name):
            def run(campaign_id, script, attempt, prev):
                calls.append(name)
                if name not in ok:
                    raise RuntimeError(f"{name} unavailable")
                return f"{name.upper()}_RESULT"

            return run

        monkeypatch.setattr(tracks, "_run_tts_tokenrouter", make("tokenrouter"))
        monkeypatch.setattr(tracks, "_run_tts_deepgram", make("deepgram"))
        monkeypatch.setattr(tracks, "_run_tts_elevenlabs", make("elevenlabs"))
        # rebuild the dispatch table against the patched runners
        monkeypatch.setattr(
            tracks,
            "_TTS_BACKENDS",
            {
                "tokenrouter": (tracks._run_tts_tokenrouter, lambda s: True, lambda s: "TR"),
                "deepgram": (tracks._run_tts_deepgram, lambda s: True, lambda s: "DG"),
                "elevenlabs": (tracks._run_tts_elevenlabs, lambda s: True, lambda s: "EL"),
            },
        )
        return calls

    def _auto(self, monkeypatch):
        monkeypatch.setenv("FERNWOOD_TTS_PROVIDER", "auto")
        from app.config import get_settings

        get_settings.cache_clear()

    def test_auto_order_is_tokenrouter_deepgram_elevenlabs(self):
        from app.pipeline.tracks import _AUTO_ORDER

        assert _AUTO_ORDER == ("tokenrouter", "deepgram", "elevenlabs")

    def test_prefers_tokenrouter(self, monkeypatch):
        self._auto(monkeypatch)
        from app.pipeline import tracks

        calls = self._patch(monkeypatch, ok={"tokenrouter", "deepgram", "elevenlabs"})
        _, backend, _ = tracks._run_tts("c", "hi", 1, None)
        assert backend == "tokenrouter" and calls == ["tokenrouter"]

    def test_falls_back_to_deepgram(self, monkeypatch):
        self._auto(monkeypatch)
        from app.pipeline import tracks

        calls = self._patch(monkeypatch, ok={"deepgram", "elevenlabs"})
        _, backend, _ = tracks._run_tts("c", "hi", 1, None)
        assert backend == "deepgram"
        assert calls == ["tokenrouter", "deepgram"]

    def test_falls_through_to_elevenlabs_last(self, monkeypatch):
        self._auto(monkeypatch)
        from app.pipeline import tracks

        calls = self._patch(monkeypatch, ok={"elevenlabs"})
        _, backend, _ = tracks._run_tts("c", "hi", 1, None)
        assert backend == "elevenlabs"
        assert calls == ["tokenrouter", "deepgram", "elevenlabs"]

    def test_all_down_raises_the_last_error(self, monkeypatch):
        self._auto(monkeypatch)
        from app.pipeline import tracks

        self._patch(monkeypatch, ok=set())
        with pytest.raises(RuntimeError):
            tracks._run_tts("c", "hi", 1, None)

    def test_explicit_backend_does_not_fall_back(self, monkeypatch):
        """Pinning a backend must stay pinned — silent substitution would hide
        a misconfiguration."""
        monkeypatch.setenv("FERNWOOD_TTS_PROVIDER", "deepgram")
        from app.config import get_settings
        from app.pipeline import tracks

        get_settings.cache_clear()
        calls = self._patch(monkeypatch, ok={"tokenrouter", "elevenlabs"})
        with pytest.raises(RuntimeError):
            tracks._run_tts("c", "hi", 1, None)
        assert calls == ["deepgram"]
        get_settings.cache_clear()
