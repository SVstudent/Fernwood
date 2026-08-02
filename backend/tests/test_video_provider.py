"""TokenRouterVideoProvider — the async submit/poll/fetch_output lifecycle.

Video is the one integration whose upstream is genuinely asynchronous, so unlike
the image provider this subclasses BaseProvider and implements the three-method
lifecycle directly. These tests pin the state machine and the per-provider
first-frame field mapping without spending video quota.
"""

from __future__ import annotations

import httpx
import pytest
from genblaze_core.exceptions import ProviderError
from genblaze_core.models.enums import ProviderErrorCode
from genblaze_core.models.step import Step
from genblaze_core.providers import BaseProvider, SubmitResult

from app.providers.tokenrouter_video import TokenRouterVideoProvider, image_field_for

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512


@pytest.fixture
def provider():
    return TokenRouterVideoProvider(api_key="k", base_url="https://api.example/v1")


def _step(**params) -> Step:
    return Step(
        provider="tokenrouter-video",
        model=params.pop("model", "MiniMax-Hailuo-2.3"),
        prompt="a slow push-in",
        params=params,
    )


class TestLifecycleContract:
    def test_is_an_async_base_provider_not_a_sync_one(self):
        """The image provider is a SyncProvider because its API is synchronous;
        video is genuinely task-based, so it implements the real lifecycle."""
        from genblaze_core.providers import SyncProvider

        assert issubclass(TokenRouterVideoProvider, BaseProvider)
        assert not issubclass(TokenRouterVideoProvider, SyncProvider)

    def test_implements_all_three_abstract_methods(self):
        assert not TokenRouterVideoProvider.__abstractmethods__
        for name in ("submit", "poll", "fetch_output"):
            assert name in TokenRouterVideoProvider.__dict__


class TestSubmit:
    def test_returns_task_id_with_timing_hint(self, provider, monkeypatch):
        captured = {}

        def fake_post(url, headers=None, json=None):
            captured.update(json)
            return httpx.Response(200, json={"task_id": "task_abc", "status": "queued"})

        monkeypatch.setattr(provider, "_post_submit", None, raising=False)
        monkeypatch.setattr(
            httpx.Client, "post", lambda self, url, headers=None, json=None: fake_post(url, headers, json)
        )
        result = provider.submit(_step())
        assert isinstance(result, SubmitResult)
        assert result.prediction_id == "task_abc"
        assert result.estimated_seconds and result.estimated_seconds > 0
        assert captured["duration"] == 6
        assert captured["size"] == "768P"

    def test_missing_task_id_raises(self, provider, monkeypatch):
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, headers=None, json=None: httpx.Response(200, json={"nope": 1}),
        )
        with pytest.raises(ProviderError, match="No task_id"):
            provider.submit(_step())

    def test_http_error_is_classified(self, provider, monkeypatch):
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, headers=None, json=None: httpx.Response(
                401, json={"error": {"message": "Invalid token"}}
            ),
        )
        with pytest.raises(ProviderError) as exc:
            provider.submit(_step())
        assert exc.value.error_code == ProviderErrorCode.AUTH_FAILURE


class TestImageToVideoFieldMapping:
    @pytest.mark.parametrize(
        "model,field",
        [
            ("MiniMax-Hailuo-2.3", "first_frame_image"),
            ("kling-v3", "image"),
            ("kling-3.0-turbo", "image"),
            ("happyhorse-1.0-i2v", "input_reference"),
            ("dreamina-seedance-2-0-fast", "images"),
        ],
    )
    def test_per_provider_first_frame_field(self, model, field):
        """Providers disagree on the field name; TokenRouter documents the map."""
        assert image_field_for(model) == field

    def test_seedance_field_is_array_valued(self, provider, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, headers=None, json=None: (
                captured.update(json),
                httpx.Response(200, json={"task_id": "t"}),
            )[1],
        )
        provider.submit(
            _step(model="dreamina-seedance-2-0", source_image_url="https://cdn/x.jpg")
        )
        assert captured["images"] == ["https://cdn/x.jpg"]

    def test_hailuo_field_is_scalar(self, provider, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, headers=None, json=None: (
                captured.update(json),
                httpx.Response(200, json={"task_id": "t"}),
            )[1],
        )
        provider.submit(_step(source_image_url="https://cdn/x.jpg"))
        assert captured["first_frame_image"] == "https://cdn/x.jpg"

    def test_non_https_first_frame_rejected(self, provider):
        """validate_asset_url is https-only — an SSRF guard."""
        with pytest.raises(Exception):
            provider.submit(_step(source_image_url="file:///etc/passwd"))


def _poll_response(status, **extra):
    return httpx.Response(200, json={"code": "success", "data": {"status": status, **extra}})


class TestPoll:
    @pytest.mark.parametrize("status", ["NOT_START", "PROCESSING", "QUEUED", "IN_PROGRESS"])
    def test_non_terminal_states_keep_polling(self, provider, monkeypatch, status):
        monkeypatch.setattr(
            httpx.Client, "get", lambda self, url, headers=None: _poll_response(status)
        )
        assert provider.poll("task_1") is False

    @pytest.mark.parametrize("status", ["SUCCESS", "SUCCEEDED", "COMPLETED"])
    def test_success_is_terminal(self, provider, monkeypatch, status):
        monkeypatch.setattr(
            httpx.Client,
            "get",
            lambda self, url, headers=None: _poll_response(status, result_url="https://cdn/v.mp4"),
        )
        assert provider.poll("task_1") is True

    @pytest.mark.parametrize("status", ["FAILED", "ERROR", "CANCELED", "TIMEOUT"])
    def test_failure_is_also_terminal(self, provider, monkeypatch, status):
        """poll() returns True on failure too — the base contract is 'done',
        not 'succeeded'. fetch_output() raises."""
        monkeypatch.setattr(
            httpx.Client, "get", lambda self, url, headers=None: _poll_response(status)
        )
        assert provider.poll("task_1") is True

    def test_status_is_read_from_nested_data(self, provider, monkeypatch):
        """This gateway nests the task object under `data`."""
        monkeypatch.setattr(
            httpx.Client,
            "get",
            lambda self, url, headers=None: httpx.Response(
                200, json={"code": "success", "data": {"status": "SUCCESS"}}
            ),
        )
        assert provider.poll("t") is True

    def test_flat_payload_also_supported(self, provider, monkeypatch):
        monkeypatch.setattr(
            httpx.Client,
            "get",
            lambda self, url, headers=None: httpx.Response(200, json={"status": "SUCCESS"}),
        )
        assert provider.poll("t") is True


class TestFetchOutput:
    def _wire(self, monkeypatch, provider, payload, body=MP4):
        monkeypatch.setattr(
            httpx.Client, "get", lambda self, url, headers=None: (
                httpx.Response(200, json={"data": payload})
                if "/video/generations/" in url
                else httpx.Response(200, content=body, headers={"content-type": "video/mp4"})
            )
        )

    def test_downloads_hashes_and_attaches_asset(self, provider, monkeypatch):
        self._wire(
            monkeypatch, provider, {"status": "SUCCESS", "result_url": "https://cdn/v.mp4"}
        )
        step = _step()
        out = provider.fetch_output("task_1", step)
        asset = out.assets[0]
        assert asset.media_type == "video/mp4"
        assert len(asset.sha256) == 64
        assert asset.size_bytes == len(MP4)
        assert asset.url.startswith("file://")
        assert out.metadata["task_id"] == "task_1"

    def test_asset_lands_under_the_system_temp_dir(self, provider, monkeypatch):
        """ObjectStorageSink reads file:// assets only from gettempdir()."""
        import tempfile
        from pathlib import Path

        self._wire(
            monkeypatch, provider, {"status": "SUCCESS", "result_url": "https://cdn/v.mp4"}
        )
        step = _step()
        provider.fetch_output("task_1", step)
        # Resolve BOTH sides: on macOS gettempdir() reports /var/... while
        # Path.resolve() follows the symlink to /private/var/... . The emitted
        # asset URL is resolved, and genblaze resolves incoming paths too, so
        # resolved-vs-resolved mirrors the sink's actual check.
        path = Path(step.metadata["local_path"]).resolve()
        assert path.is_relative_to(Path(tempfile.gettempdir()).resolve())
        assert step.assets[0].url.startswith("file://")

    def test_failed_task_raises_with_reason(self, provider, monkeypatch):
        self._wire(
            monkeypatch,
            provider,
            {"status": "FAILED", "fail_reason": "content policy"},
        )
        with pytest.raises(ProviderError, match="content policy"):
            provider.fetch_output("task_1", _step())

    def test_success_without_result_url_raises(self, provider, monkeypatch):
        self._wire(monkeypatch, provider, {"status": "SUCCESS"})
        with pytest.raises(ProviderError, match="no result_url"):
            provider.fetch_output("task_1", _step())

    def test_oversized_video_rejected(self, provider, monkeypatch):
        self._wire(
            monkeypatch,
            provider,
            {"status": "SUCCESS", "result_url": "https://cdn/v.mp4"},
            body=b"x" * (201 * 1024 * 1024),
        )
        with pytest.raises(ProviderError, match="size cap"):
            provider.fetch_output("task_1", _step())


class TestVideoPrompt:
    def test_directs_motion_and_preserves_composition(self, brief):
        """The still already passed critique — the prompt must animate it, not
        redraw it."""
        from app.domain.prompts import build_video_prompt

        p = build_video_prompt(brief)
        assert "Fernwood Goods" in p
        low = p.lower()
        assert "do not add, remove or redesign" in low
        assert "no text" in low
        assert "#" not in p  # same hex-rendering hazard as stills
