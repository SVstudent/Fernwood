"""TokenRouter providers: response parsing and error classification.

_extract_image is the highest-risk code in the project — TokenRouter does not
document its image envelope, so the parser accepts a superset of shapes. Each
one is pinned here.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from genblaze_core.exceptions import ProviderError
from genblaze_core.models.enums import ProviderErrorCode

from app.providers.tokenrouter_image import (
    TokenRouterImageProvider,
    _classify,
    _err_msg,
)

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
B64 = base64.b64encode(PNG_1PX).decode()


@pytest.fixture
def provider():
    return TokenRouterImageProvider(api_key="k", base_url="https://api.example/v1")


class TestExtractImage:
    """Every envelope shape the gateway is known or suspected to emit."""

    def test_documented_shape_data_url(self, provider, monkeypatch):
        monkeypatch.setattr(
            provider, "_download", lambda url: (PNG_1PX, "image/png")
        )
        raw, mt, src = provider._extract_image(
            {"created": 1, "data": [{"url": "https://cdn/x.png", "size": "2560x1440"}]}
        )
        assert raw == PNG_1PX and mt == "image/png" and src == "url"

    def test_b64_json(self, provider):
        raw, mt, src = provider._extract_image({"data": [{"b64_json": B64}]})
        assert raw == PNG_1PX and src == "b64_json"

    @pytest.mark.parametrize("field", ["b64", "image_base64"])
    def test_b64_aliases(self, provider, field):
        raw, _, _ = provider._extract_image({"data": [{field: B64}]})
        assert raw == PNG_1PX

    def test_images_container(self, provider, monkeypatch):
        monkeypatch.setattr(provider, "_download", lambda url: (PNG_1PX, "image/png"))
        raw, _, _ = provider._extract_image({"images": [{"url": "https://cdn/a.png"}]})
        assert raw == PNG_1PX

    def test_nested_result_data(self, provider):
        raw, _, _ = provider._extract_image({"result": {"data": [{"b64_json": B64}]}})
        assert raw == PNG_1PX

    def test_image_url_object(self, provider, monkeypatch):
        monkeypatch.setattr(provider, "_download", lambda url: (PNG_1PX, "image/png"))
        raw, _, _ = provider._extract_image(
            {"data": [{"image_url": {"url": "https://cdn/a.png"}}]}
        )
        assert raw == PNG_1PX

    def test_data_uri(self, provider):
        raw, mt, src = provider._extract_image(
            {"data": [{"url": f"data:image/jpeg;base64,{B64}"}]}
        )
        assert raw == PNG_1PX and mt == "image/jpeg" and src == "data-uri"

    def test_bare_string_b64(self, provider):
        raw, _, src = provider._extract_image({"data": [B64]})
        assert raw == PNG_1PX and src == "b64_json"

    def test_top_level_url(self, provider, monkeypatch):
        monkeypatch.setattr(provider, "_download", lambda url: (PNG_1PX, "image/png"))
        raw, _, _ = provider._extract_image({"url": "https://cdn/a.png"})
        assert raw == PNG_1PX

    def test_empty_response_raises_with_diagnostic_keys(self, provider):
        """A live parse failure must be diagnosable in seconds."""
        with pytest.raises(ProviderError) as exc:
            provider._extract_image({"weird": 1, "other": 2})
        assert "other" in str(exc.value) and "weird" in str(exc.value)

    def test_item_without_url_or_b64_raises(self, provider):
        with pytest.raises(ProviderError):
            provider._extract_image({"data": [{"revised_prompt": "x"}]})

    def test_malformed_b64_raises_provider_error(self, provider):
        with pytest.raises(ProviderError):
            provider._decode_b64("!!!not base64!!!" * 5)


class TestErrorClassification:
    @pytest.mark.parametrize(
        "status,expected",
        [
            (401, ProviderErrorCode.AUTH_FAILURE),
            (403, ProviderErrorCode.AUTH_FAILURE),
            (404, ProviderErrorCode.MODEL_ERROR),
            (429, ProviderErrorCode.RATE_LIMIT),
            (408, ProviderErrorCode.TIMEOUT),
            (504, ProviderErrorCode.TIMEOUT),
            (400, ProviderErrorCode.INVALID_INPUT),
            (500, ProviderErrorCode.SERVER_ERROR),
            (503, ProviderErrorCode.SERVER_ERROR),
            (418, ProviderErrorCode.UNKNOWN),
        ],
    )
    def test_status_mapping(self, status, expected):
        assert _classify(status) == expected

    def test_all_codes_exist_on_the_installed_enum(self):
        """Guards against the enum member names drifting between releases."""
        for name in (
            "TIMEOUT",
            "RATE_LIMIT",
            "AUTH_FAILURE",
            "INVALID_INPUT",
            "MODEL_ERROR",
            "SERVER_ERROR",
            "UNKNOWN",
        ):
            assert hasattr(ProviderErrorCode, name)

    def test_err_msg_extracts_openai_shape(self):
        resp = httpx.Response(
            400,
            content=json.dumps(
                {"error": {"message": "size must be at least 3686400 pixels"}}
            ),
            headers={"content-type": "application/json"},
        )
        assert "3686400" in _err_msg(resp)

    def test_err_msg_survives_non_json(self):
        resp = httpx.Response(502, content=b"<html>bad gateway</html>")
        assert "html" in _err_msg(resp)


class TestRequestPayload:
    def test_defaults_match_upstream_constraints(self, provider, monkeypatch):
        """2560x1440 is seedream's exact minimum (3,686,400 px) and 16:9;
        watermark must be off or the render carries an 'AI generated' badge."""
        captured = {}

        def fake_post(payload):
            captured.update(payload)
            return {"data": [{"b64_json": B64}]}

        monkeypatch.setattr(provider, "_post", fake_post)

        from genblaze_core.models.step import Step

        step = Step(provider="tokenrouter-image", model="seedream", prompt="p")
        provider.generate(step)

        assert captured["size"] == "2560x1440"
        w, h = (int(x) for x in captured["size"].split("x"))
        assert w * h >= 3_686_400
        assert captured["watermark"] is False
        assert captured["n"] == 1

    def test_params_override_defaults(self, provider, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            provider,
            "_post",
            lambda p: (captured.update(p), {"data": [{"b64_json": B64}]})[1],
        )
        from genblaze_core.models.step import Step

        step = Step(
            provider="tokenrouter-image",
            model="m",
            prompt="p",
            params={"size": "2048x2048", "watermark": True},
        )
        provider.generate(step)
        assert captured["size"] == "2048x2048"
        assert captured["watermark"] is True


class TestGenerateEmitsValidAsset:
    def test_asset_is_file_uri_under_temp_with_sha256(self, provider, monkeypatch):
        """file:// under gettempdir() is mandatory — ObjectStorageSink reads
        local assets only from there. sha256 must be set so manifests verify."""
        import tempfile
        from pathlib import Path

        monkeypatch.setattr(provider, "_post", lambda p: {"data": [{"b64_json": B64}]})
        from genblaze_core.models.step import Step

        step = Step(provider="tokenrouter-image", model="m", prompt="p")
        out = provider.generate(step)

        asset = out.assets[0]
        assert asset.url.startswith("file://")
        path = Path(asset.url.replace("file://", ""))
        # Compare RESOLVED paths: on macOS gettempdir() reports /var/... while
        # Path.resolve() follows the symlink to /private/var/... . genblaze's
        # ALLOWED_FILE_ROOTS resolves too, so resolved-vs-resolved is the
        # comparison that actually mirrors the sink's check.
        assert path.is_relative_to(Path(tempfile.gettempdir()).resolve())
        assert len(asset.sha256) == 64
        assert asset.size_bytes == len(PNG_1PX)
        assert out.metadata["local_path"]


class TestChatStepTemperatureGuard:
    def test_anthropic_models_drop_temperature(self):
        """anthropic/* returns HTTP 400: '`temperature` is deprecated for this
        model.' Verified against the live gateway."""
        from app.providers.client import NO_TEMPERATURE_PREFIXES

        assert "anthropic/" in NO_TEMPERATURE_PREFIXES
        assert "anthropic/claude-opus-5".startswith(NO_TEMPERATURE_PREFIXES)
        assert not "openai/gpt-5.4".startswith(NO_TEMPERATURE_PREFIXES)
