"""TokenRouterImageProvider — custom Genblaze Provider for TokenRouter images.

JUDGMENT CALL 1 — base class. The brief asked for submit/poll/fetch_output, but
docs/guides/new-provider.md says: "Use SyncProvider unless your API requires
polling. Most providers are sync," and maps synchronous APIs to
SyncProvider.generate(). TokenRouter's POST /v1/images/generations IS
synchronous — their docs read result["data"][0]["url"] straight off the POST
response, and only their *video* endpoint documents task polling. SyncProvider
implements submit/poll/fetch_output on our behalf (submit() calls generate() and
stashes the Step, poll() returns True, fetch_output() pops it), so we still get
exactly that lifecycle via the idiomatic base class.

JUDGMENT CALL 2 — response parsing. TokenRouter does not document the image
response envelope beyond `data[0].url`. Their own web client accepts a superset
(url / b64_json / nested containers), so _extract_image walks every shape rather
than assuming one. Parse failures log the actual top-level keys so a live
failure is diagnosable in seconds.

JUDGMENT CALL 3 — we download the bytes inside generate() and set sha256
ourselves. URL expiry is undocumented, so the CDN URL is treated as ephemeral.
Setting sha256 here means Manifest.verify() passes even without a sink, and the
vision-critique step reuses the same local bytes instead of re-fetching.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import mimetypes
from typing import Any
from urllib.parse import urlparse

import httpx
from genblaze_core.exceptions import ProviderError
from genblaze_core.models.asset import Asset
from genblaze_core.models.enums import ProviderErrorCode
from genblaze_core.models.step import Step
from genblaze_core.providers import SyncProvider, validate_asset_url

from app.config import SCRATCH_DIR

logger = logging.getLogger(__name__)

_MAX_BYTES = 25 * 1024 * 1024


def _classify(status: int) -> ProviderErrorCode:
    """Map HTTP status onto genblaze's error taxonomy.

    Member names verified against the installed enum:
    TIMEOUT, RATE_LIMIT, AUTH_FAILURE, INVALID_INPUT, MODEL_ERROR,
    SERVER_ERROR, CONTENT_POLICY, UNKNOWN. (There is no NETWORK member.)
    """
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


def _err_msg(resp: httpx.Response) -> str:
    """TokenRouter returns OpenAI-shaped {"error":{"message","type","code"}}."""
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:300]
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err)[:300]
    return str(body)[:300]


class TokenRouterImageProvider(SyncProvider):
    """Synchronous image generation via TokenRouter POST /v1/images/generations."""

    name = "tokenrouter-image"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        # 180s was too tight: seedream at 2560x1440 intermittently exceeded it
        # and surfaced a provider error mid-run. Must stay BELOW the pipeline
        # step timeout in tracks.py so the provider's own error (with a useful
        # message) wins over a generic pipeline timeout.
        request_timeout: float = 300.0,
        **kwargs: Any,
    ) -> None:
        # BaseProvider.__init__ is keyword-only (models, retry_policy,
        # probe_cache_ttl, probe_cache_max_entries).
        super().__init__(**kwargs)
        self._api_key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = request_timeout

    # ------------------------------------------------------------------
    def generate(self, step: Step, config: Any = None) -> Step:
        params = step.params or {}
        payload: dict[str, Any] = {
            "model": step.model,
            "prompt": step.prompt or "",
            "n": 1,
            # 2560x1440 = 3,686,400 px, which is EXACTLY seedream's documented
            # minimum ("image size must be at least 3686400 pixels" — verified
            # by probe; 1024x1024 is rejected with HTTP 400). It is also 16:9,
            # matching the aspect ratio the campaign UI renders.
            "size": params.get("size", "2560x1440"),
            # Seedream stamps a visible "AI generated" badge by default, which
            # the vision critique correctly flagged as making the asset
            # unusable as-shipped (capping Technical Clarity ~72/80). The
            # upstream field is a real bool — passing a string returns a Go
            # unmarshal error naming `watermark` of type bool.
            "watermark": params.get("watermark", False),
        }
        for key in ("quality", "background", "response_format", "seed"):
            if key in params and params[key] is not None:
                payload[key] = params[key]

        data = self._post(payload)
        raw, media_type, source = self._extract_image(data)

        SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
        ext = mimetypes.guess_extension(media_type) or ".png"
        if ext == ".jpe":  # mimetypes quirk
            ext = ".jpg"
        out = SCRATCH_DIR / f"{step.step_id}{ext}"
        out.write_bytes(raw)

        asset = Asset(
            # file:// under tempfile.gettempdir() — required, because
            # ObjectStorageSink reads local assets via _read_local_file(),
            # which allows only {gettempdir(), /tmp} and exposes no way to
            # widen that. Do NOT run validate_asset_url() on this: it is
            # https-only and would reject file://.
            url=out.resolve().as_uri(),
            media_type=media_type,
            sha256=hashlib.sha256(raw).hexdigest(),
            size_bytes=len(raw),
        )
        try:
            from PIL import Image

            with Image.open(out) as im:
                asset.width, asset.height = im.size
        except Exception:  # noqa: BLE001 - dimensions are cosmetic
            pass

        asset.metadata.update({"source": source, "upstream_model": step.model})
        step.assets.append(asset)
        step.metadata["local_path"] = str(out)
        return step

    # ---- HTTP --------------------------------------------------------
    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}/images/generations"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"TokenRouter image request timed out after {self._timeout}s",
                error_code=ProviderErrorCode.TIMEOUT,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"TokenRouter transport error: {exc}",
                error_code=ProviderErrorCode.SERVER_ERROR,
            ) from exc

        if resp.status_code >= 400:
            raise ProviderError(
                f"TokenRouter {resp.status_code} on {payload['model']}: {_err_msg(resp)}",
                error_code=_classify(resp.status_code),
            )

        try:
            body = resp.json()
        except ValueError as exc:
            raise ProviderError(
                f"TokenRouter returned non-JSON: {resp.text[:200]}",
                error_code=ProviderErrorCode.UNKNOWN,
            ) from exc
        if not isinstance(body, dict):
            raise ProviderError(
                f"TokenRouter returned {type(body).__name__}, expected object",
                error_code=ProviderErrorCode.UNKNOWN,
            )
        return body

    # ---- defensive response parsing ----------------------------------
    def _extract_image(self, data: dict[str, Any]) -> tuple[bytes, str, str]:
        candidates: list[Any] = []
        for container in ("data", "images", "output"):
            value = data.get(container)
            if isinstance(value, list):
                candidates.extend(value)
        nested = data.get("result")
        if isinstance(nested, dict) and isinstance(nested.get("data"), list):
            candidates.extend(nested["data"])
        if not candidates and isinstance(data.get("url"), str):
            candidates.append(data)

        if not candidates:
            raise ProviderError(
                f"No image payload in TokenRouter response; top-level keys={sorted(data)[:12]}",
                error_code=ProviderErrorCode.UNKNOWN,
            )

        for item in candidates:
            if isinstance(item, str):
                if item.startswith("http"):
                    payload, mtype = self._download(item)
                    return payload, mtype, "url"
                if item.startswith("data:"):
                    return (*self._decode_data_uri(item), "data-uri")
                return self._decode_b64(item), "image/png", "b64_json"

            if not isinstance(item, dict):
                continue

            b64 = item.get("b64_json") or item.get("b64") or item.get("image_base64")
            if isinstance(b64, str) and b64:
                return self._decode_b64(b64), "image/png", "b64_json"

            url = item.get("url")
            if not url:
                image_url = item.get("image_url")
                url = image_url.get("url") if isinstance(image_url, dict) else image_url
            if isinstance(url, str) and url:
                if url.startswith("data:"):
                    return (*self._decode_data_uri(url), "data-uri")
                payload, mtype = self._download(url)
                return payload, mtype, "url"

        raise ProviderError(
            f"TokenRouter response had no url/b64_json; item keys="
            f"{[sorted(i) for i in candidates if isinstance(i, dict)][:3]}",
            error_code=ProviderErrorCode.UNKNOWN,
        )

    def _download(self, url: str) -> tuple[bytes, str]:
        # https-only SSRF guard, per the new-provider guide. Applied to the
        # upstream CDN URL only — never to the file:// we emit.
        validate_asset_url(url)
        try:
            with httpx.Client(timeout=self._timeout, follow_redirects=True) as client:
                resp = client.get(url)
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Failed to download generated image: {exc}",
                error_code=ProviderErrorCode.SERVER_ERROR,
            ) from exc
        if resp.status_code >= 400:
            raise ProviderError(
                f"Asset CDN returned {resp.status_code} for {urlparse(url).netloc}",
                error_code=_classify(resp.status_code),
            )
        if len(resp.content) > _MAX_BYTES:
            raise ProviderError(
                f"Generated image exceeds {_MAX_BYTES} byte cap",
                error_code=ProviderErrorCode.INVALID_INPUT,
            )
        ctype = resp.headers.get("content-type", "image/png").split(";")[0].strip()
        return resp.content, ctype or "image/png"

    @staticmethod
    def _decode_data_uri(uri: str) -> tuple[bytes, str]:
        head, _, payload = uri.partition(",")
        media_type = head[5:].split(";")[0] or "image/png"
        return TokenRouterImageProvider._decode_b64(payload), media_type

    @staticmethod
    def _decode_b64(value: str) -> bytes:
        try:
            return base64.b64decode(value, validate=False)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                "Malformed base64 image payload from TokenRouter",
                error_code=ProviderErrorCode.UNKNOWN,
            ) from exc
