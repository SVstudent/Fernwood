"""TokenRouter TTS provider and voiceover backend selection.

Context: ElevenLabs' free tier is 10,000 characters/month. Once spent it returns
auth_failure on every call and the audio track dies mid-run — observed live at
9,983/10,000. TokenRouter's `openai/gpt-audio-mini` serves as the primary
backend, with ElevenLabs optional and automatically fallen back over.
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import httpx
import pytest
from genblaze_core.exceptions import ProviderError
from genblaze_core.models.enums import ProviderErrorCode
from genblaze_core.models.step import Step

from app.providers.tokenrouter_tts import VOICES, TokenRouterTTSProvider

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" + b"\x00" * 2048
B64 = base64.b64encode(MP3).decode()


@pytest.fixture
def provider():
    return TokenRouterTTSProvider(api_key="k", base_url="https://api.example/v1")


def _step(**params) -> Step:
    return Step(
        provider="tokenrouter-tts",
        model=params.pop("model", "openai/gpt-audio-mini"),
        prompt=params.pop("prompt", "At Fernwood Goods, mornings begin slower."),
        params=params,
    )


def _ok(body):
    return httpx.Response(200, json=body)


class TestRequestShape:
    def test_requests_audio_modality(self, provider, monkeypatch):
        """Audio-out-over-chat is the only TTS route TokenRouter exposes;
        /v1/audio/speech returns 503 model_not_found."""
        captured = {}
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, headers=None, json=None: (
                captured.update({"url": url, **json}),
                _ok({"choices": [{"message": {"audio": {"data": B64}}}]}),
            )[1],
        )
        provider.generate(_step())
        assert captured["url"].endswith("/chat/completions")
        assert captured["modalities"] == ["text", "audio"]
        assert captured["audio"]["format"] == "mp3"
        assert captured["audio"]["voice"] == "ash"

    def test_voice_is_configurable(self, provider, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, headers=None, json=None: (
                captured.update(json),
                _ok({"choices": [{"message": {"audio": {"data": B64}}}]}),
            )[1],
        )
        provider.generate(_step(voice="sage"))
        assert captured["audio"]["voice"] == "sage"

    def test_script_is_framed_as_narration(self, provider, monkeypatch):
        """It is a chat model — without instruction it answers the script
        instead of reading it."""
        captured = {}
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, headers=None, json=None: (
                captured.update(json),
                _ok({"choices": [{"message": {"audio": {"data": B64}}}]}),
            )[1],
        )
        provider.generate(_step(prompt="Hello world."))
        content = captured["messages"][0]["content"].lower()
        assert "read" in content and "exactly as written" in content
        assert "Hello world." in captured["messages"][0]["content"]

    def test_empty_script_rejected(self, provider):
        with pytest.raises(ProviderError) as exc:
            provider.generate(_step(prompt="   "))
        assert exc.value.error_code == ProviderErrorCode.INVALID_INPUT

    def test_known_voices(self):
        assert "ash" in VOICES and "alloy" in VOICES


class TestResponseParsing:
    def test_standard_audio_field(self, provider, monkeypatch):
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, headers=None, json=None: _ok(
                {"choices": [{"message": {"audio": {"data": B64}}}]}
            ),
        )
        step = _step()
        out = provider.generate(step)
        asset = out.assets[0]
        assert asset.media_type == "audio/mpeg"
        assert asset.size_bytes == len(MP3)
        assert len(asset.sha256) == 64

    def test_audio_nested_in_content_parts(self, provider, monkeypatch):
        """Tolerate gateways that inline audio as a content part."""
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, headers=None, json=None: _ok(
                {
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {"type": "text", "text": "ok"},
                                    {"type": "audio", "audio": {"data": B64}},
                                ]
                            }
                        }
                    ]
                }
            ),
        )
        assert provider.generate(_step()).assets[0].size_bytes == len(MP3)

    def test_text_only_reply_raises_clearly(self, provider, monkeypatch):
        """A chat model can answer in text — that must be a loud error, not a
        zero-byte 'success'."""
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, headers=None, json=None: _ok(
                {"choices": [{"message": {"content": "Sure! Here you go."}}]}
            ),
        )
        with pytest.raises(ProviderError, match="no audio payload"):
            provider.generate(_step())

    def test_malformed_envelope_raises(self, provider, monkeypatch):
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, headers=None, json=None: _ok({"unexpected": True}),
        )
        with pytest.raises(ProviderError, match="Unexpected TTS response"):
            provider.generate(_step())

    def test_asset_written_under_system_temp(self, provider, monkeypatch):
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, headers=None, json=None: _ok(
                {"choices": [{"message": {"audio": {"data": B64}}}]}
            ),
        )
        step = _step()
        provider.generate(step)
        path = Path(step.metadata["local_path"]).resolve()
        assert path.is_relative_to(Path(tempfile.gettempdir()).resolve())
        assert step.assets[0].url.startswith("file://")

    @pytest.mark.parametrize(
        "status,code",
        [
            (401, ProviderErrorCode.AUTH_FAILURE),
            (429, ProviderErrorCode.RATE_LIMIT),
            (503, ProviderErrorCode.SERVER_ERROR),
        ],
    )
    def test_http_errors_classified(self, provider, monkeypatch, status, code):
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, headers=None, json=None: httpx.Response(
                status, json={"error": {"message": "nope"}}
            ),
        )
        with pytest.raises(ProviderError) as exc:
            provider.generate(_step())
        assert exc.value.error_code == code


class TestBackendSelection:
    """_run_tts must never leave a campaign without a voiceover just because
    one vendor's quota ran out."""

    def _patch(self, monkeypatch, el_ok: bool, tr_ok: bool):
        calls = []

        def el(campaign_id, script, attempt, prev):
            calls.append("elevenlabs")
            if not el_ok:
                raise RuntimeError("ElevenLabs TTS failed (code=auth_failure)")
            return "EL_RESULT"

        def tr(campaign_id, script, attempt, prev):
            calls.append("tokenrouter")
            if not tr_ok:
                raise RuntimeError("tokenrouter down")
            return "TR_RESULT"

        from app.pipeline import tracks

        monkeypatch.setattr(tracks, "_run_tts_elevenlabs", el)
        monkeypatch.setattr(tracks, "_run_tts_tokenrouter", tr)
        return calls

    def test_default_uses_tokenrouter_only(self, monkeypatch):
        monkeypatch.setenv("FERNWOOD_TTS_PROVIDER", "tokenrouter")
        from app.config import get_settings
        from app.pipeline import tracks

        get_settings.cache_clear()
        calls = self._patch(monkeypatch, el_ok=True, tr_ok=True)
        result, backend, label = tracks._run_tts("c", "hello", 1, None)
        assert backend == "tokenrouter" and calls == ["tokenrouter"]
        assert "TokenRouter" in label
        get_settings.cache_clear()

    def test_auto_prefers_elevenlabs_when_keyed(self, monkeypatch):
        monkeypatch.setenv("FERNWOOD_TTS_PROVIDER", "auto")
        monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_test")
        from app.config import get_settings
        from app.pipeline import tracks

        get_settings.cache_clear()
        calls = self._patch(monkeypatch, el_ok=True, tr_ok=True)
        _, backend, _ = tracks._run_tts("c", "hello", 1, None)
        assert backend == "elevenlabs" and calls == ["elevenlabs"]
        get_settings.cache_clear()

    def test_auto_falls_back_when_quota_exhausted(self, monkeypatch):
        """The scenario that broke a live run."""
        monkeypatch.setenv("FERNWOOD_TTS_PROVIDER", "auto")
        monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_test")
        from app.config import get_settings
        from app.pipeline import tracks

        get_settings.cache_clear()
        calls = self._patch(monkeypatch, el_ok=False, tr_ok=True)
        _, backend, _ = tracks._run_tts("c", "hello", 1, None)
        assert backend == "tokenrouter"
        assert calls == ["elevenlabs", "tokenrouter"]
        get_settings.cache_clear()

    def test_auto_skips_elevenlabs_without_a_key(self, monkeypatch):
        monkeypatch.setenv("FERNWOOD_TTS_PROVIDER", "auto")
        monkeypatch.setenv("ELEVENLABS_API_KEY", "")
        from app.config import get_settings
        from app.pipeline import tracks

        get_settings.cache_clear()
        calls = self._patch(monkeypatch, el_ok=True, tr_ok=True)
        _, backend, _ = tracks._run_tts("c", "hello", 1, None)
        assert backend == "tokenrouter" and calls == ["tokenrouter"]
        get_settings.cache_clear()

    def test_all_backends_failing_raises(self, monkeypatch):
        monkeypatch.setenv("FERNWOOD_TTS_PROVIDER", "auto")
        monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_test")
        from app.config import get_settings
        from app.pipeline import tracks

        get_settings.cache_clear()
        self._patch(monkeypatch, el_ok=False, tr_ok=False)
        with pytest.raises(Exception):
            tracks._run_tts("c", "hello", 1, None)
        get_settings.cache_clear()
