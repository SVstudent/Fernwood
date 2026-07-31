"""Probe TokenRouter with a real key BEFORE trusting any assumption.

Prints the raw JSON envelope from /v1/images/generations so the provider's
defensive parser can be checked against reality rather than speculation, and
confirms which image/vision models this key can actually reach.

Run:  cd backend && uv run python scripts/probe_tokenrouter.py
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.providers.client import (  # noqa: E402
    CHAT_CANDIDATES,
    IMAGE_CANDIDATES,
    VISION_CANDIDATES,
)

# 8x8 red PNG — smallest possible real image for a multimodal probe.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAHUlEQVQoU2P8z8Dwn4Ei"
    "wDiqgWEwhAFjNBoGQxgAAI7QB/2sHDKzAAAAAElFTkSuQmCC"
)


def main() -> int:
    s = get_settings()
    if not s.has_tokenrouter:
        print("TOKENROUTER_API_KEY is not set in .env — nothing to probe.")
        return 1

    base = s.tokenrouter_base_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {s.tokenrouter_api_key}",
        "Content-Type": "application/json",
    }

    print("=" * 70)
    print("1. GET /v1/models")
    print("=" * 70)
    available: set[str] = set()
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{base}/models", headers=headers)
        print(f"HTTP {r.status_code}")
        if r.status_code < 400:
            body = r.json()
            available = {m.get("id", "") for m in body.get("data", [])}
            print(f"{len(available)} models reachable")
            for group, name in (
                (IMAGE_CANDIDATES, "IMAGE"),
                (VISION_CANDIDATES, "VISION"),
                (CHAT_CANDIDATES, "CHAT"),
            ):
                hits = [m for m in group if m in available]
                print(f"  {name:7s} candidates present: {hits or 'NONE — will fall back'}")
        else:
            print(r.text[:400])
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc}")

    print()
    print("=" * 70)
    print("2. POST /v1/images/generations  (the critical unknown)")
    print("=" * 70)
    model = s.fernwood_image_model or next(
        (m for m in IMAGE_CANDIDATES if m in available), IMAGE_CANDIDATES[0]
    )
    print(f"model = {model}")
    try:
        with httpx.Client(timeout=180) as c:
            r = c.post(
                f"{base}/images/generations",
                headers=headers,
                json={
                    "model": model,
                    "prompt": "A single ceramic bowl on a linen cloth, warm morning light.",
                    "n": 1,
                    "size": "1024x1024",
                },
            )
        print(f"HTTP {r.status_code}")
        try:
            body = r.json()
        except ValueError:
            print("non-JSON response:", r.text[:400])
            body = None
        if isinstance(body, dict):
            print(f"top-level keys: {sorted(body)}")
            redacted = json.dumps(body)
            # Truncate any base64 blobs so the output stays readable
            if len(redacted) > 1200:
                print("(envelope truncated)")
                for k, v in body.items():
                    if isinstance(v, list) and v:
                        item = v[0]
                        if isinstance(item, dict):
                            print(f"  {k}[0] keys: {sorted(item)}")
                            for ik, iv in item.items():
                                prev = str(iv)[:90]
                                print(f"    {ik}: {prev}{'...' if len(str(iv)) > 90 else ''}")
                        else:
                            print(f"  {k}[0]: {str(item)[:120]}")
                    elif not isinstance(v, (list, dict)):
                        print(f"  {k}: {v}")
            else:
                print(json.dumps(body, indent=2)[:1200])
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc}")

    print()
    print("=" * 70)
    print("3. POST /v1/chat/completions with an image (vision critique path)")
    print("=" * 70)
    vmodel = s.fernwood_vision_model or next(
        (m for m in VISION_CANDIDATES if m in available), VISION_CANDIDATES[0]
    )
    print(f"model = {vmodel}")
    data_uri = "data:image/png;base64," + base64.b64encode(TINY_PNG).decode()
    try:
        with httpx.Client(timeout=90) as c:
            r = c.post(
                f"{base}/chat/completions",
                headers=headers,
                json={
                    "model": vmodel,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "What colour is this image? One word."},
                                {"type": "image_url", "image_url": {"url": data_uri}},
                            ],
                        }
                    ],
                    "max_tokens": 20,
                },
            )
        print(f"HTTP {r.status_code}")
        if r.status_code < 400:
            body = r.json()
            msg = body.get("choices", [{}])[0].get("message", {}).get("content")
            print(f"MULTIMODAL OK -> {str(msg)[:120]}")
        else:
            print("vision failed:", r.text[:400])
            print(">>> Critique will degrade to text-only. Try another VISION_CANDIDATE.")
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
