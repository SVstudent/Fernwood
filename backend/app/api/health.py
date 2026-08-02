"""Pre-demo sanity check. Hit this before you present."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from app.config import Resolved, get_settings
from app.providers.client import tokenrouter_client

router = APIRouter(tags=["health"])


def _probe_tokenrouter() -> dict:
    s = get_settings()
    if not s.has_tokenrouter:
        return {"configured": False, "reachable": False, "models": 0}
    try:
        page = tokenrouter_client().models.list()
        return {"configured": True, "reachable": True, "models": len(page.data)}
    except Exception as exc:  # noqa: BLE001
        return {"configured": True, "reachable": False, "error": str(exc)[:200]}


@router.get("/health")
async def health() -> dict:
    s = get_settings()
    tr = await asyncio.to_thread(_probe_tokenrouter)
    warnings = list(Resolved.warnings)
    if s.fernwood_storage == "b2" and not s.has_b2:
        warnings.append("FERNWOOD_STORAGE=b2 but B2 credentials are missing.")

    return {
        "ok": tr.get("reachable", False),
        "storage": {
            "mode": s.fernwood_storage,
            "bucket": s.b2_bucket if s.fernwood_storage == "b2" else str(s.local_root),
            "b2Configured": s.has_b2,
        },
        "tokenrouter": {
            **tr,
            "imageModel": Resolved.image_model,
            "visionModel": Resolved.vision_model,
            "chatModel": Resolved.chat_model,
        },
        "voiceover": {
            "provider": s.fernwood_tts_provider,
            "enabled": s.fernwood_enable_tts,
            "tokenrouterModel": s.fernwood_tts_model,
            "tokenrouterVoice": s.fernwood_tts_voice,
            "deepgramConfigured": s.has_deepgram,
            "deepgramVoice": s.deepgram_tts_model,
            "elevenlabsConfigured": s.has_elevenlabs,
        },
        "elevenlabs": {
            "configured": s.has_elevenlabs,
            "enabled": s.fernwood_enable_tts,
            "model": s.elevenlabs_model,
        },
        "pipeline": {
            "maxAttempts": s.fernwood_max_attempts,
            "passThreshold": s.fernwood_pass_threshold,
            "forceFirstRetry": s.fernwood_force_first_retry,
        },
        "warnings": warnings,
    }
