"""Live integration tests — hit the real TokenRouter / ElevenLabs / B2 APIs.

Skipped by default. These cost money and take minutes.

    uv run pytest tests/test_live_integration.py -m live -v

They exist because the offline suite cannot catch upstream contract drift: the
image size floor, the watermark default, which models actually return usable
JSON, and whether B2 credentials still work. Each of those has already broken
once during development.
"""

from __future__ import annotations

import base64
import io
import json

import httpx
import pytest

from app.config import get_settings
from app.providers.client import (
    IMAGE_CANDIDATES,
    VISION_CANDIDATES,
    probe_models,
    tokenrouter_client,
)

pytestmark = pytest.mark.live


def _settings():
    return get_settings()


needs_tokenrouter = pytest.mark.skipif(
    not _settings().has_tokenrouter, reason="TOKENROUTER_API_KEY not set"
)
needs_elevenlabs = pytest.mark.skipif(
    not _settings().has_elevenlabs, reason="ELEVENLABS_API_KEY not set"
)
needs_b2 = pytest.mark.skipif(not _settings().has_b2, reason="B2 credentials not set")


def _tiny_jpeg() -> str:
    from PIL import Image

    im = Image.new("RGB", (256, 256), (30, 58, 43))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


@needs_tokenrouter
class TestTokenRouterContract:
    def test_models_endpoint_reachable(self):
        ids = {m.id for m in tokenrouter_client().models.list().data}
        assert len(ids) > 10

    def test_at_least_one_image_candidate_available(self):
        ids = {m.id for m in tokenrouter_client().models.list().data}
        assert set(IMAGE_CANDIDATES) & ids, "no configured image model is reachable"

    def test_at_least_one_vision_candidate_available(self):
        ids = {m.id for m in tokenrouter_client().models.list().data}
        assert set(VISION_CANDIDATES) & ids

    def test_probe_resolves_all_three_roles(self):
        probe_models()
        from app.config import Resolved

        assert Resolved.image_model and Resolved.vision_model and Resolved.chat_model

    def test_image_size_floor_still_applies(self):
        """seedream rejects < 3,686,400 px. If upstream relaxes this, our
        2560x1440 default is still valid — but we want to know."""
        s = _settings()
        r = httpx.post(
            f"{s.tokenrouter_base_url.rstrip('/')}/images/generations",
            headers={"Authorization": f"Bearer {s.tokenrouter_api_key}"},
            json={
                "model": IMAGE_CANDIDATES[0],
                "prompt": "a bowl",
                "n": 1,
                "size": "512x512",
            },
            timeout=120,
        )
        assert r.status_code == 400
        assert "3686400" in r.text or "size" in r.text.lower()

    def test_vision_model_returns_non_empty_structured_json(self):
        """The silent-failure guard: gemini answers 200 with EMPTY content on
        multimodal requests, which would fake every critique."""
        from app.config import Resolved
        from app.pipeline.schemas import CRITIQUE_SCHEMA

        probe_models()
        s = _settings()
        r = httpx.post(
            f"{s.tokenrouter_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {s.tokenrouter_api_key}"},
            json={
                "model": Resolved.vision_model,
                "max_tokens": 1200,
                "response_format": CRITIQUE_SCHEMA,
                "messages": [
                    {"role": "system", "content": "Respond only with JSON."},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Critique this image briefly."},
                            {"type": "image_url", "image_url": {"url": _tiny_jpeg()}},
                        ],
                    },
                ],
            },
            timeout=120,
        )
        assert r.status_code == 200
        text = r.json()["choices"][0]["message"]["content"]
        assert text and text.strip(), "vision model returned EMPTY content"
        parsed = json.loads(text)
        assert isinstance(parsed["overallScore"], int)
        assert len(parsed["criteria"]) >= 3


@needs_tokenrouter
class TestLiveImageProvider:
    def test_generates_a_real_decodable_image(self):
        from PIL import Image
        from genblaze_core.models.step import Step

        from app.config import Resolved
        from app.providers.tokenrouter_image import TokenRouterImageProvider

        probe_models()
        s = _settings()
        provider = TokenRouterImageProvider(
            api_key=s.tokenrouter_api_key, base_url=s.tokenrouter_base_url
        )
        step = Step(
            provider="tokenrouter-image",
            model=Resolved.image_model,
            prompt="A single deep forest green ceramic bowl on near-white linen.",
        )
        out = provider.generate(step)
        asset = out.assets[0]

        assert len(asset.sha256) == 64
        path = out.metadata["local_path"]
        with Image.open(path) as im:
            assert im.size == (2560, 1440)  # 16:9 at the pixel floor


def _elevenlabs_quota_left() -> int | None:
    """Characters remaining on the ElevenLabs plan, or None if unknown."""
    s = _settings()
    if not s.has_elevenlabs:
        return None
    try:
        r = httpx.get(
            "https://api.elevenlabs.io/v1/user/subscription",
            headers={"xi-api-key": s.elevenlabs_api_key},
            timeout=20,
        )
        if r.status_code >= 400:
            return None
        d = r.json()
        return int(d["character_limit"]) - int(d["character_count"])
    except Exception:  # noqa: BLE001
        return None


@needs_tokenrouter
class TestLiveTokenRouterTTS:
    """The default voiceover backend — one key, no monthly character cliff."""

    def test_synthesises_playable_mp3(self):
        import io

        from genblaze_core import Modality, Pipeline
        from mutagen.mp3 import MP3

        from app.providers.tokenrouter_tts import TokenRouterTTSProvider
        from app.storage.factory import make_sink

        s = _settings()
        result = (
            Pipeline("live-tr-tts", tenant_id="fernwood", preflight=False)
            .step(
                TokenRouterTTSProvider(
                    api_key=s.tokenrouter_api_key, base_url=s.tokenrouter_base_url
                ),
                model=s.fernwood_tts_model,
                prompt="Fernwood Goods. Made slowly, made to last.",
                modality=Modality.AUDIO,
                voice=s.fernwood_tts_voice,
            )
            .run(sink=make_sink("camp-live-tr-tts"), timeout=300, raise_on_failure=True)
        )
        asset = result.run.steps[0].assets[0]
        assert asset.media_type == "audio/mpeg"
        assert asset.size_bytes and asset.size_bytes > 5_000
        assert len(asset.sha256) == 64
        assert result.manifest.verify() is True

        # Read straight from the storage backend rather than over HTTP: the
        # test process points storage at a throwaway root, so its public URL
        # host does not resolve.
        from app.storage.factory import get_backend

        backend = get_backend()
        raw = backend.get(backend.key_from_url(asset.url))
        info = MP3(io.BytesIO(raw)).info
        assert info.length > 1.0, "audio is implausibly short"
        assert raw[:3] == b"ID3" or raw[:2] == b"\xff\xfb"

    def test_configured_model_supports_audio_output(self):
        """gpt-audio (non-mini) rejects this with 'requires stream: true' —
        guard against the default drifting to a model that cannot do it."""
        s = _settings()
        r = httpx.post(
            f"{s.tokenrouter_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {s.tokenrouter_api_key}"},
            json={
                "model": s.fernwood_tts_model,
                "modalities": ["text", "audio"],
                "audio": {"voice": s.fernwood_tts_voice, "format": "mp3"},
                "messages": [{"role": "user", "content": "Say: hello."}],
            },
            timeout=180,
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["choices"][0]["message"].get("audio", {}).get("data")


@needs_elevenlabs
class TestLiveElevenLabs:
    """Optional backend. Skips (rather than fails) when the free-tier character
    allowance is spent — that is an account state, not a regression, and the
    pipeline falls back to TokenRouter automatically."""

    def test_synthesises_playable_mp3(self):
        remaining = _elevenlabs_quota_left()
        if remaining is not None and remaining < 200:
            pytest.skip(
                f"ElevenLabs quota exhausted ({remaining} chars left) — "
                "pipeline falls back to TokenRouter TTS"
            )
        from genblaze_core import Modality, Pipeline
        from genblaze_elevenlabs import ElevenLabsTTSProvider

        from app.storage.factory import make_sink

        s = _settings()
        result = (
            Pipeline("live-tts", tenant_id="fernwood", preflight=False)
            .step(
                # No output_dir on purpose: the default writes under the system
                # temp dir, the only place ObjectStorageSink may read file://
                # assets from.
                ElevenLabsTTSProvider(api_key=s.elevenlabs_api_key),
                model=s.elevenlabs_model,
                prompt="Fernwood Goods. Made slowly, made to last.",
                modality=Modality.AUDIO,
                voice_id=s.elevenlabs_voice_id,
                output_format="mp3_44100_128",
            )
            .run(sink=make_sink("camp-live-tts"), timeout=180, raise_on_failure=True)
        )
        asset = result.run.steps[0].assets[0]
        assert asset.media_type in ("audio/mpeg", "audio/mp3")
        assert asset.size_bytes and asset.size_bytes > 10_000
        assert len(asset.sha256) == 64
        assert result.manifest.verify() is True


@needs_b2
class TestLiveBackblazeB2:
    def _backend(self):
        from genblaze_s3 import S3StorageBackend

        s = _settings()
        return S3StorageBackend.for_backblaze(
            s.b2_bucket,
            region=s.b2_region,
            key_id=s.b2_key_id,
            app_key=s.b2_app_key,
            auto_lifecycle=False,
            preflight=True,
        )

    def test_credentials_are_s3_capable(self):
        """A B2 MASTER key (12-char id) is rejected by the S3 API with
        'Malformed Access Key Id' — only a 25-char application key works."""
        assert len(_settings().b2_key_id) == 25, (
            "B2_KEY_ID looks like a master key; create a non-master "
            "application key for S3 access"
        )

    def test_put_get_delete_roundtrip(self):
        backend = self._backend()
        key = "fernwood/_pytest_live_check.txt"
        backend.put(key, b"live check", content_type="text/plain")
        assert backend.get(key) == b"live check"
        assert backend.exists(key)
        backend.delete(key)
        assert not backend.exists(key)

    def test_presigned_url_works_on_private_bucket(self):
        backend = self._backend()
        key = "fernwood/_pytest_presign.txt"
        backend.put(key, b"presign", content_type="text/plain")
        try:
            url = backend.get_url(key, expires_in=300)
            assert httpx.get(url, timeout=30).content == b"presign"
        finally:
            backend.delete(key)
