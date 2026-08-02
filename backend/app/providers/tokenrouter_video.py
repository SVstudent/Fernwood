"""TokenRouterVideoProvider — asynchronous Genblaze Provider for video.

THIS is the case the original brief described. Unlike image generation (which is
synchronous, so it uses SyncProvider), TokenRouter's video API is a genuine
async task flow:

    POST /v1/video/generations        -> {"task_id": "task_..."}
    GET  /v1/video/generations/{id}   -> {"data": {"status": ..., "result_url": ...}}

docs/guides/new-provider.md maps exactly that onto BaseProvider's
submit / poll / fetch_output lifecycle, so this subclasses BaseProvider directly:

    submit()       -> returns the provider's task_id
    poll()         -> True once the task reaches a TERMINAL state (success OR failure)
    fetch_output() -> downloads the mp4, hashes it, attaches the Asset

Verified against the live API: status goes NOT_START -> ... -> SUCCESS, and
result_url is nested under `data`. Typical latency 90-130s.

IMAGE-TO-VIDEO: the source image URL must be publicly fetchable by TokenRouter's
upstream. Providers disagree on the field name, so _image_field() maps it:
    Hailuo    -> first_frame_image
    Kling     -> image
    Seedance  -> images (array)
    Happyhorse-> input_reference
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
from genblaze_core.providers import BaseProvider, SubmitResult, validate_asset_url

from app.config import SCRATCH_DIR
from app.providers.tokenrouter_image import _classify, _err_msg

logger = logging.getLogger(__name__)

_MAX_BYTES = 200 * 1024 * 1024

# Terminal states, verified live. Anything else means "keep polling".
_SUCCESS = {"SUCCESS", "SUCCEEDED", "COMPLETED", "FINISHED"}
_FAILURE = {"FAILED", "FAIL", "ERROR", "CANCELED", "CANCELLED", "TIMEOUT"}


def image_field_for(model: str) -> str:
    """Per-provider first-frame field name (documented in TokenRouter's video guide)."""
    m = model.lower()
    if m.startswith("kling"):
        return "image"
    if "happyhorse" in m:
        return "input_reference"
    if "seedance" in m or "dreamina" in m:
        return "images"  # array-valued
    return "first_frame_image"  # Hailuo and the general default


class TokenRouterVideoProvider(BaseProvider):
    """Asynchronous video generation via TokenRouter's task API."""

    name = "tokenrouter-video"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        request_timeout: float = 120.0,
        download_timeout: float = 300.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._api_key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = request_timeout
        self._download_timeout = download_timeout
        # fetch_output() receives only (prediction_id, step), so the terminal
        # poll payload is cached here rather than re-fetched.
        self._last_payload: dict[str, dict[str, Any]] = {}

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    # ---- 1. submit ---------------------------------------------------
    def submit(self, step: Step, config: Any = None) -> Any:
        params = step.params or {}
        payload: dict[str, Any] = {
            "model": step.model,
            "prompt": step.prompt or "",
            "duration": params.get("duration", 6),
            "size": params.get("size", "768P"),
        }

        source_image = params.get("source_image_url")
        if source_image:
            validate_asset_url(source_image)  # https-only SSRF guard
            field = image_field_for(step.model)
            payload[field] = [source_image] if field == "images" else source_image

        if isinstance(params.get("metadata"), dict):
            payload["metadata"] = params["metadata"]

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    f"{self._base}/video/generations",
                    headers=self._headers,
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"TokenRouter video submit failed: {exc}",
                error_code=ProviderErrorCode.SERVER_ERROR,
            ) from exc

        if resp.status_code >= 400:
            raise ProviderError(
                f"TokenRouter video {resp.status_code} on {step.model}: {_err_msg(resp)}",
                error_code=_classify(resp.status_code),
            )

        body = resp.json()
        task_id = (
            body.get("task_id")
            or body.get("id")
            or (body.get("data") or {}).get("task_id")
        )
        if not task_id:
            raise ProviderError(
                f"No task_id in submit response; keys={sorted(body)[:12]}",
                error_code=ProviderErrorCode.UNKNOWN,
            )

        logger.info("video task %s submitted (%s)", task_id, step.model)
        # estimated_seconds lets the runner back off sensibly instead of
        # hammering the poll endpoint; ~115s observed for 6s/768P.
        return SubmitResult(prediction_id=task_id, estimated_seconds=110.0)

    # ---- 2. poll -----------------------------------------------------
    def poll(self, prediction_id: Any, config: Any = None) -> bool:
        """True when TERMINAL (success or failure) — per the base-class contract.
        fetch_output() is responsible for turning a failure into an error."""
        payload = self._query(prediction_id)
        status = self._status_of(payload)
        if status in _SUCCESS or status in _FAILURE:
            self._last_payload[str(prediction_id)] = payload
            return True
        logger.debug("video task %s: %s (%s)", prediction_id, status, payload.get("progress"))
        return False

    # ---- 3. fetch_output ---------------------------------------------
    def fetch_output(self, prediction_id: Any, step: Step) -> Step:
        payload = self._last_payload.pop(str(prediction_id), None) or self._query(
            prediction_id
        )
        status = self._status_of(payload)

        if status in _FAILURE:
            reason = payload.get("fail_reason") or payload.get("error") or status
            raise ProviderError(
                f"TokenRouter video task {prediction_id} failed: {reason}",
                error_code=ProviderErrorCode.MODEL_ERROR,
            )

        url = (
            payload.get("result_url")
            or payload.get("video_url")
            or payload.get("url")
            or (payload.get("result") or {}).get("url")
        )
        if not url:
            raise ProviderError(
                f"Video task succeeded but no result_url; keys={sorted(payload)[:12]}",
                error_code=ProviderErrorCode.UNKNOWN,
            )

        raw = self._download(str(url))
        SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
        out = SCRATCH_DIR / f"{step.step_id}.mp4"
        out.write_bytes(raw)

        asset = Asset(
            # file:// under the system temp dir — the only place
            # ObjectStorageSink is permitted to read local assets from.
            url=out.resolve().as_uri(),
            media_type="video/mp4",
            sha256=hashlib.sha256(raw).hexdigest(),
            size_bytes=len(raw),
        )
        asset.metadata.update(
            {"upstream_model": step.model, "task_id": str(prediction_id)}
        )
        step.assets.append(asset)
        step.metadata["local_path"] = str(out)
        step.metadata["task_id"] = str(prediction_id)
        return step

    # ---- helpers -----------------------------------------------------
    def _query(self, task_id: Any) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(
                    f"{self._base}/video/generations/{task_id}", headers=self._headers
                )
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"TokenRouter video poll failed: {exc}",
                error_code=ProviderErrorCode.SERVER_ERROR,
            ) from exc
        if resp.status_code >= 400:
            raise ProviderError(
                f"TokenRouter video poll {resp.status_code}: {_err_msg(resp)}",
                error_code=_classify(resp.status_code),
            )
        body = resp.json()
        # The task object is nested under `data` on this gateway; tolerate flat.
        inner = body.get("data")
        return inner if isinstance(inner, dict) else body

    @staticmethod
    def _status_of(payload: dict[str, Any]) -> str:
        return str(
            payload.get("status") or payload.get("task_status") or ""
        ).upper()

    def _download(self, url: str) -> bytes:
        validate_asset_url(url)
        try:
            with httpx.Client(
                timeout=self._download_timeout, follow_redirects=True
            ) as client:
                resp = client.get(url)
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Failed to download generated video: {exc}",
                error_code=ProviderErrorCode.SERVER_ERROR,
            ) from exc
        if resp.status_code >= 400:
            raise ProviderError(
                f"Video CDN returned {resp.status_code}",
                error_code=_classify(resp.status_code),
            )
        if len(resp.content) > _MAX_BYTES:
            raise ProviderError(
                "Generated video exceeds size cap",
                error_code=ProviderErrorCode.INVALID_INPUT,
            )
        return resp.content
