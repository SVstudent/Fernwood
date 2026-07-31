"""Per-asset generate -> critique -> retry tracks.

DESIGN CALL: one Pipeline.run() per ATTEMPT, three independent tracks.

Why per-attempt rather than one reused Pipeline:
  * A Pipeline is declared then executed as a unit; the retry prompt does not
    exist until the previous critique has come back. There is no in-Pipeline
    conditional-rerun primitive.
  * Manifest is per-Run. One run per attempt = one manifest per attempt = the
    "attempt #1 rejected, attempt #2 approved" provenance chain that is the
    entire point of this project. A single reused Pipeline would collapse all
    attempts into one manifest.
  * ObjectStorageSink is single-use — Pipeline.run() closes it in a finally
    block — so a fresh sink per run is the sanctioned lifecycle anyway.

Attempt N+1 links to attempt N via Pipeline.from_result(), which sets
parent_run_id and is excluded from the canonical hash, so lineage does not
perturb verification.

Why three separate tracks rather than one combined pipeline: independent retry
budgets (an image failure must not re-run copy), and fail_fast would otherwise
let an ElevenLabs blip abort everything. They run sequentially because
PipelineRunView derives a single progress percentage from the latest log's
stage — interleaving would make the bar jump backwards.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from genblaze_core import Modality, Pipeline

from app.config import Resolved, get_settings
from app.domain.models import (
    Asset,
    AssetType,
    Attempt,
    AttemptContent,
    CampaignBrief,
    CritiqueResult,
)
from app.domain.prompts import build_copy_prompt, build_image_prompt, build_voiceover_prompt
from app.pipeline.critique import critique_asset
from app.pipeline.schemas import COPY_SCHEMA, VOICEOVER_SCHEMA, loads_lenient
from app.providers.tokenrouter_chat import TokenRouterChatStep, step_text
from app.providers.tokenrouter_image import TokenRouterImageProvider
from app.runtime.logbus import Emitter, now_iso
from app.storage.factory import make_sink, public_media_url

logger = logging.getLogger(__name__)

PROVIDER_LABEL = {
    "image": "TokenRouter Image (Genblaze Provider)",
    "audio": "ElevenLabs TTS (Genblaze Provider)",
    "copy": "TokenRouter Chat (Genblaze Provider)",
}


def _local_path(step: Any) -> Path | None:
    raw = (step.metadata or {}).get("local_path")
    return Path(raw) if raw else None


# ---------------------------------------------------------------- image
def _run_image_attempt(campaign_id: str, brief: CampaignBrief, prompt: str, attempt: int, prev):
    s = get_settings()
    pipe = Pipeline(
        f"{campaign_id}-image-attempt-{attempt}",
        tenant_id="fernwood",
        project_id=campaign_id,
        preflight=False,  # our TokenRouter slugs are in no ModelRegistry
    )
    if prev is not None:
        pipe = pipe.from_result(prev)  # parent_run_id lineage across retries
    return pipe.step(
        TokenRouterImageProvider(
            api_key=s.tokenrouter_api_key, base_url=s.tokenrouter_base_url
        ),
        model=Resolved.image_model,
        prompt=prompt,
        modality=Modality.IMAGE,
        metadata={
            "campaign_id": campaign_id,
            "asset_type": "image",
            "attempt_number": attempt,
            # Step.metadata IS included in the canonical hash, so the attempt
            # number is cryptographically covered rather than merely implied
            # by a filename.
        },
        params={"size": "1024x1024"},
    ).run(sink=make_sink(campaign_id), timeout=240, raise_on_failure=True)


# ---------------------------------------------------------------- text
def _run_chat_attempt(
    campaign_id: str,
    asset_type: AssetType,
    prompt: str,
    attempt: int,
    schema: dict,
    prev,
):
    pipe = Pipeline(
        f"{campaign_id}-{asset_type}-attempt-{attempt}",
        tenant_id="fernwood",
        project_id=campaign_id,
        preflight=False,
    )
    if prev is not None:
        pipe = pipe.from_result(prev)
    return pipe.step(
        TokenRouterChatStep(),
        model=Resolved.chat_model,
        prompt=prompt,
        modality=Modality.TEXT,
        metadata={
            "campaign_id": campaign_id,
            "asset_type": asset_type,
            "attempt_number": attempt,
        },
        params={
            "response_format": schema,
            "temperature": 0.8,
            "max_tokens": 1400,
            "system": "You are a senior brand copywriter. Respond only with JSON.",
        },
    ).run(sink=make_sink(campaign_id), timeout=120, raise_on_failure=True)


# ---------------------------------------------------------------- audio
def _run_tts(campaign_id: str, script: str, attempt: int, prev):
    from genblaze_elevenlabs import ElevenLabsTTSProvider

    s = get_settings()
    pipe = Pipeline(
        f"{campaign_id}-audio-tts-{attempt}",
        tenant_id="fernwood",
        project_id=campaign_id,
        preflight=False,
    )
    if prev is not None:
        pipe = pipe.from_result(prev)
    return pipe.step(
        # No output_dir: the default writes via mkstemp under the system temp
        # dir, which is where ObjectStorageSink is allowed to read file://
        # assets from. Pointing it elsewhere fails the upload.
        ElevenLabsTTSProvider(api_key=s.elevenlabs_api_key),
        model=s.elevenlabs_model,
        prompt=script,
        modality=Modality.AUDIO,
        metadata={
            "campaign_id": campaign_id,
            "asset_type": "audio",
            "attempt_number": attempt,
        },
        params={"voice_id": s.elevenlabs_voice_id, "output_format": "mp3_44100_128"},
    ).run(sink=make_sink(campaign_id), timeout=180, raise_on_failure=True)


# ---------------------------------------------------------------- driver
def run_track(
    asset_type: AssetType,
    brief: CampaignBrief,
    campaign_id: str,
    emit: Emitter,
) -> Asset:
    """Generate -> critique -> retry for one asset type. Mirrors the mock's flow."""
    settings = get_settings()
    max_attempts = max(1, settings.fernwood_max_attempts)

    attempts: list[Attempt] = []
    last_critique: CritiqueResult | None = None
    prev_result = None
    passed = False

    emit.info(
        f"{asset_type}_gen",
        f"Generating {asset_type.upper()} Asset",
        f"Invoking Genblaze pipeline for initial {asset_type} draft...",
        asset_type=asset_type,
    )

    for n in range(1, max_attempts + 1):
        try:
            content, prompt, model_name, result = _generate(
                asset_type, brief, campaign_id, n, last_critique, prev_result, emit
            )
        except Exception as exc:  # noqa: BLE001 - provider failure, not a critique fail
            logger.exception("%s generation failed on attempt %d", asset_type, n)
            emit.error(
                f"{asset_type}_gen",
                f"{asset_type.upper()} Generation Failed (Attempt #{n})",
                f"Provider call failed: {exc}",
                asset_type=asset_type,
            )
            if n >= max_attempts:
                break
            continue

        prev_result = result

        emit.info(
            f"{asset_type}_critique",
            f"Critiquing {asset_type.upper()} (Attempt #{n})",
            f"Evaluating generated {asset_type} against brief guidelines and mood targets...",
            asset_type=asset_type,
        )

        image_path = _local_path(result.run.steps[0]) if asset_type == "image" else None
        text_blob = None
        if asset_type != "image":
            text_blob = json.dumps(content.ts(), ensure_ascii=False, indent=2)

        critique, _chash, _curi = critique_asset(
            asset_type,
            campaign_id=campaign_id,
            brief=brief,
            attempt=n,
            image_path=image_path,
            text_content=text_blob,
        )
        last_critique = critique

        attempt = Attempt(
            id=f"att-{asset_type}-{campaign_id}-{n}",
            attempt_number=n,
            provider_name=PROVIDER_LABEL[asset_type],
            model_name=model_name,
            prompt_used=prompt,
            timestamp=now_iso(),
            critique_verdict="PASS" if critique.passed else "FAIL",
            critique=critique,
            content=content,
        )
        attempts.append(attempt)

        if critique.passed:
            passed = True
            emit.success(
                f"{asset_type}_critique",
                f"{asset_type.upper()} Passed Critique (Attempt #{n})",
                f"Score: {critique.overall_score}/100. {critique.reasoning}",
                attempt=attempt,
                asset_type=asset_type,
            )
            break

        emit.warning(
            f"{asset_type}_critique",
            f"Attempt #{n} Rejected (Score: {critique.overall_score}/100)",
            f"{critique.reasoning} Retrying with adjusted prompt...",
            attempt=attempt,
            asset_type=asset_type,
        )

    # Unlike the mock (which marked the last failed attempt as approved),
    # nothing is "approved" unless it actually passed. If everything failed we
    # surface the best-scoring attempt but keep status='failed'.
    approved_id = None
    if passed and attempts:
        approved_id = attempts[-1].id
    elif attempts:
        approved_id = max(attempts, key=lambda a: a.critique.overall_score).id

    return Asset(
        id=f"asset-{asset_type}-{campaign_id}",
        campaign_id=campaign_id,
        type=asset_type,
        attempts=attempts,
        final_approved_attempt_id=approved_id,
        status="passed" if passed else "failed",
    )


def _generate(
    asset_type: AssetType,
    brief: CampaignBrief,
    campaign_id: str,
    n: int,
    last_critique: CritiqueResult | None,
    prev_result,
    emit: Emitter,
) -> tuple[AttemptContent, str, str, Any]:
    """Dispatch one generation attempt. Returns (content, prompt, model, result)."""
    settings = get_settings()

    if asset_type == "image":
        prompt = build_image_prompt(brief, n, last_critique)
        result = _run_image_attempt(campaign_id, brief, prompt, n, prev_result)
        asset = result.run.steps[0].assets[0]
        content = AttemptContent(
            image_url=public_media_url(asset.url),
            aspect_ratio="1:1",
            primary_color=brief.colors.primary,
            secondary_color=brief.colors.secondary,
            accent_color=brief.colors.accent,
            manifest_hash=result.manifest.canonical_hash,
            manifest_uri=result.manifest.manifest_uri,
        )
        return content, prompt, Resolved.image_model, result

    if asset_type == "copy":
        prompt = build_copy_prompt(brief, n, last_critique)
        result = _run_chat_attempt(campaign_id, "copy", prompt, n, COPY_SCHEMA, prev_result)
        parsed = loads_lenient(step_text(result.run.steps[0])) or {}
        content = AttemptContent(
            headline=str(parsed.get("headline") or f"{brief.brand_name}"),
            subheadline=str(parsed.get("subheadline") or brief.product_service),
            body_text=str(parsed.get("bodyText") or ""),
            call_to_action=str(parsed.get("callToAction") or "Learn more"),
            key_benefit_bullets=[str(x) for x in (parsed.get("keyBenefitBullets") or [])],
            social_posts=[str(x) for x in (parsed.get("socialPosts") or [])],
            manifest_hash=result.manifest.canonical_hash,
            manifest_uri=result.manifest.manifest_uri,
        )
        return content, prompt, Resolved.chat_model, result

    # audio: script (TokenRouter chat) -> speech (ElevenLabs)
    prompt = build_voiceover_prompt(brief, n, last_critique)
    script_result = _run_chat_attempt(
        campaign_id, "audio", prompt, n, VOICEOVER_SCHEMA, prev_result
    )
    parsed = loads_lenient(step_text(script_result.run.steps[0])) or {}
    script = str(parsed.get("script") or "").strip()
    voice_desc = str(parsed.get("voiceDescription") or "Brand voice")
    if not script:
        script = f"{brief.brand_name}. {brief.product_service}."

    content = AttemptContent(
        audio_script=script,
        audio_voice=voice_desc,
        audio_waveform_data=[15, 30, 65, 80, 45, 90, 75, 40, 85, 95, 50, 30, 15],
        manifest_hash=script_result.manifest.canonical_hash,
        manifest_uri=script_result.manifest.manifest_uri,
    )
    model_name = Resolved.chat_model

    if settings.fernwood_enable_tts and settings.has_elevenlabs:
        try:
            tts_result = _run_tts(campaign_id, script, n, script_result)
            audio_asset = tts_result.run.steps[0].assets[0]
            content.audio_url = public_media_url(audio_asset.url)
            content.duration_seconds = getattr(audio_asset, "duration", None)
            content.manifest_hash = tts_result.manifest.canonical_hash
            content.manifest_uri = tts_result.manifest.manifest_uri
            model_name = f"{settings.elevenlabs_model} + {Resolved.chat_model}"
            return content, prompt, model_name, tts_result
        except Exception as exc:  # noqa: BLE001 - degrade to script-only
            logger.warning("TTS failed on attempt %d: %s", n, exc)
            emit.warning(
                "audio_gen",
                "Voiceover Synthesis Unavailable",
                f"Script generated, but ElevenLabs synthesis failed: {exc}",
                asset_type="audio",
            )
    return content, prompt, model_name, script_result
