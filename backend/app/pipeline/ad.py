"""The advertisement track: storyboard -> per-shot frames -> clips -> final cut.

This replaces the original brand-film track, which animated the single approved
key visual. That produced a technically real video and a creatively empty one —
one still, drifting. An advertisement cuts between scenes, and this track makes
that literal:

    1. STORYBOARD   an LLM writes 3-4 shots against the campaign's own strategy,
                    copy and voiceover (app/pipeline/storyboard.py)
    2. FRAMES       each shot gets its OWN generated first frame — a different
                    scene, not a re-crop of the key visual
    3. CLIPS        each frame is animated with that shot's own camera move
    4. CUT          shots are concatenated, the approved voiceover is laid over
                    the whole film, and a branded end card closes it

Shots are rendered CONCURRENTLY. The video API is a genuine task queue
(submit/poll/fetch, ~2 minutes per clip), so running three sequentially would
cost six minutes of mostly waiting. Concurrency here is not an optimisation
detail — it is what makes a four-shot ad viable in a live demo.

Degradation is stepwise rather than all-or-nothing, because each stage produces
something usable on its own:
    no storyboard model -> a structurally valid fallback shot list
    a shot fails        -> the ad is cut from the shots that rendered
    no ffmpeg           -> the longest single clip ships as the film
    no voiceover        -> the cut ships silent
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from genblaze_core import Modality, Pipeline

from app.brain.models import CampaignStrategy
from app.config import Resolved, get_settings
from app.domain.models import (
    AdShot,
    Asset,
    Attempt,
    AttemptContent,
    CampaignBrief,
    CritiqueCriterion,
    CritiqueResult,
)
from app.pipeline import assemble
from app.pipeline.storyboard import build_storyboard, fallback_storyboard
from app.runtime.logbus import Emitter, now_iso
from app.storage.factory import make_sink, public_media_url

logger = logging.getLogger(__name__)

PROVIDER_LABEL = "TokenRouter Video (Genblaze async Provider)"
_ROLE_LABEL = {
    "hook": "Hook",
    "product": "Product",
    "benefit": "Benefit",
    "cta": "Close",
}


# ------------------------------------------------------------------ helpers
def _local_path(step: Any) -> Path | None:
    raw = (step.metadata or {}).get("local_path")
    return Path(raw) if raw else None


def _key_from_public_url(url: str | None) -> str | None:
    prefix = "/api/media/"
    if url and url.startswith(prefix):
        return url[len(prefix) :]
    return None


def _presign(key: str) -> str | None:
    """Short-lived https URL so TokenRouter's upstream can fetch a first frame.

    The bucket is private so a durable URL would 403, and local disk is not
    reachable from the internet at all — hence the None, which the caller
    reports as a skipped film rather than a failure.
    """
    from app.storage.backends import LocalDiskBackend
    from app.storage.factory import get_backend

    backend = get_backend()
    if isinstance(backend, LocalDiskBackend):
        return None
    try:
        return backend.get_url(key, expires_in=3600)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not presign %s: %s", key, exc)
        return None


def _approved(asset: Asset | None):
    if asset is None or not asset.attempts:
        return None
    return next(
        (a for a in asset.attempts if a.id == asset.final_approved_attempt_id),
        max(asset.attempts, key=lambda a: a.critique.overall_score),
    )


# ------------------------------------------------------------- generation
def _render_frame(campaign_id: str, shot: AdShot) -> tuple[Path | None, str | None, str | None]:
    """Generate this shot's first frame. Returns (local_path, media_url, hash)."""
    s = get_settings()
    from app.providers.tokenrouter_image import TokenRouterImageProvider

    result = (
        Pipeline(
            f"{campaign_id}-ad-shot-{shot.index}-frame",
            tenant_id="fernwood",
            project_id=campaign_id,
            preflight=False,
        )
        .step(
            TokenRouterImageProvider(
                api_key=s.tokenrouter_api_key, base_url=s.tokenrouter_base_url
            ),
            model=Resolved.image_model,
            prompt=shot.scene_prompt,
            modality=Modality.IMAGE,
            metadata={
                "campaign_id": campaign_id,
                "asset_type": "video",
                "ad_shot_index": shot.index,
                "ad_shot_role": shot.role,
                "stage": "first_frame",
            },
            params={"size": "2560x1440"},  # 16:9 at seedream's minimum pixel count
        )
        .run(sink=make_sink(campaign_id), timeout=420, raise_on_failure=True)
    )
    step = result.run.steps[0]
    return (
        _local_path(step),
        public_media_url(step.assets[0].url),
        result.manifest.canonical_hash,
    )


def _render_clip(
    campaign_id: str, shot: AdShot, first_frame_url: str
) -> tuple[Path | None, str | None, str | None]:
    """Animate this shot's frame with its own camera move."""
    s = get_settings()
    from app.providers.tokenrouter_video import TokenRouterVideoProvider

    result = (
        Pipeline(
            f"{campaign_id}-ad-shot-{shot.index}-clip",
            tenant_id="fernwood",
            project_id=campaign_id,
            preflight=False,
        )
        .step(
            TokenRouterVideoProvider(
                api_key=s.tokenrouter_api_key, base_url=s.tokenrouter_base_url
            ),
            model=s.fernwood_video_model,
            prompt=shot.motion_prompt,
            modality=Modality.VIDEO,
            metadata={
                "campaign_id": campaign_id,
                "asset_type": "video",
                "ad_shot_index": shot.index,
                "ad_shot_role": shot.role,
                "stage": "clip",
            },
            params={
                "duration": shot.duration_seconds,
                "size": s.fernwood_video_size,
                "source_image_url": first_frame_url,
            },
        )
        .run(sink=make_sink(campaign_id), timeout=900, raise_on_failure=True)
    )
    step = result.run.steps[0]
    return (
        _local_path(step),
        public_media_url(step.assets[0].url),
        result.manifest.canonical_hash,
    )


def _produce_shot(
    campaign_id: str, shot: AdShot, emit: Emitter
) -> tuple[AdShot, Path | None]:
    """Frame then clip for one shot. Never raises — a failed shot is dropped.

    Runs on a worker thread, so it must not touch shared state beyond the
    emitter (whose registry publish is thread-safe).
    """
    label = _ROLE_LABEL.get(shot.role, shot.role.title())
    try:
        _, frame_url, frame_hash = _render_frame(campaign_id, shot)
        shot.frame_url = frame_url

        key = _key_from_public_url(frame_url)
        signed = _presign(key) if key else None
        if not signed:
            shot.status = "failed"
            emit.warning(
                "video_gen",
                f"Shot {shot.index + 1} Skipped ({label})",
                "The generated first frame could not be made fetchable by the "
                "video provider. Set FERNWOOD_STORAGE=b2 so shot frames can be "
                "presigned.",
                asset_type="video",
            )
            return shot, None

        emit.info(
            "video_gen",
            f"Shot {shot.index + 1}/{'?'} — {label}: {shot.title}",
            f"Frame rendered; animating with: {shot.motion_prompt}",
            asset_type="video",
        )

        clip_path, clip_url, clip_hash = _render_clip(campaign_id, shot, signed)
        shot.clip_url = clip_url
        shot.manifest_hash = clip_hash or frame_hash
        shot.status = "rendered"

        emit.success(
            "video_gen",
            f"Shot {shot.index + 1} Rendered — {label}",
            f'"{shot.title}" — {shot.duration_seconds}s. {shot.scene_prompt[:120]}',
            asset_type="video",
        )
        return shot, clip_path

    except Exception as exc:  # noqa: BLE001 - one shot must not kill the ad
        logger.exception("ad shot %d failed", shot.index)
        shot.status = "failed"
        emit.warning(
            "video_gen",
            f"Shot {shot.index + 1} Failed ({label})",
            f"{exc}. The advertisement will be cut from the remaining shots.",
            asset_type="video",
        )
        return shot, None


# -------------------------------------------------------------- assembly
def _assemble(
    campaign_id: str,
    brief: CampaignBrief,
    shots: list[AdShot],
    clips: list[Path],
    voiceover: Path | None,
    copy_content: Any,
    emit: Emitter,
) -> tuple[Path | None, bool, bool]:
    """Cut the shots together. Returns (final_path, had_voiceover, had_end_card)."""
    work = assemble.workdir(campaign_id)

    if assemble.ffmpeg_exe() is None:
        emit.warning(
            "assembly",
            "Shots Not Cut Together",
            "ffmpeg is unavailable, so the longest single shot is being "
            "delivered instead of the assembled advertisement.",
            asset_type="video",
        )
        return (max(clips, key=lambda p: p.stat().st_size) if clips else None), False, False

    normalized: list[Path] = []
    for i, clip in enumerate(clips):
        dst = work / f"norm-{i:02d}.mp4"
        if assemble.normalize_clip(clip, dst):
            normalized.append(dst)
    if not normalized:
        return (clips[0] if clips else None), False, False

    # End card: the only lettering in the film, drawn by us so it is spelled
    # correctly and on-brand rather than hallucinated into a frame.
    had_end_card = False
    png = work / "endcard.png"
    if assemble.end_card(
        brand_name=brief.brand_name,
        headline=getattr(copy_content, "headline", "") or brief.product_service,
        cta=getattr(copy_content, "call_to_action", "") or "",
        primary_hex=brief.colors.primary,
        accent_hex=brief.colors.accent,
        out_png=png,
    ):
        card_clip = work / "norm-99-endcard.mp4"
        if assemble.still_to_clip(png, 2.5, card_clip):
            normalized.append(card_clip)
            had_end_card = True

    cut = work / "cut.mp4"
    if not assemble.concat(normalized, cut):
        return normalized[0], False, had_end_card

    emit.success(
        "assembly",
        f"Advertisement Cut — {len(shots)} shots"
        + (" + end card" if had_end_card else ""),
        f"{len(normalized)} segments joined into one continuous film.",
        asset_type="video",
    )

    if voiceover and voiceover.is_file():
        with_audio = work / "final.mp4"
        if assemble.add_voiceover(cut, voiceover, with_audio):
            emit.success(
                "assembly",
                "Voiceover Laid Over the Cut",
                "The approved, transcription-verified voiceover now runs across "
                "the whole advertisement.",
                asset_type="video",
            )
            return with_audio, True, had_end_card
        emit.warning(
            "assembly",
            "Voiceover Could Not Be Muxed",
            "Delivering the cut silent rather than failing the film.",
            asset_type="video",
        )

    return cut, False, had_end_card


def _publish(campaign_id: str, final: Path) -> tuple[str | None, str | None]:
    """Store the finished ad as a Genblaze step so it gets its own manifest."""
    from app.providers.local_file import LocalFileProvider

    result = (
        Pipeline(
            f"{campaign_id}-ad-final",
            tenant_id="fernwood",
            project_id=campaign_id,
            preflight=False,
        )
        .step(
            LocalFileProvider(),
            model="fernwood-ad-assembler",
            prompt="Assembled multi-shot advertisement",
            modality=Modality.VIDEO,
            metadata={
                "campaign_id": campaign_id,
                "asset_type": "video",
                "stage": "assembled_ad",
            },
            params={"path": str(final), "media_type": "video/mp4"},
        )
        .run(sink=make_sink(campaign_id), timeout=420, raise_on_failure=True)
    )
    step = result.run.steps[0]
    return public_media_url(step.assets[0].url), result.manifest.canonical_hash


# ------------------------------------------------------------------ track
def run_ad_track(
    brief: CampaignBrief,
    campaign_id: str,
    emit: Emitter,
    image_asset: Asset | None,
    audio_asset: Asset | None,
    copy_asset: Asset | None,
    strategy: CampaignStrategy | None = None,
) -> Asset | None:
    """Produce a multi-shot advertisement. Returns None when video cannot run."""
    settings = get_settings()
    shot_count = max(2, min(4, settings.fernwood_ad_shots))
    seconds = settings.fernwood_video_duration

    approved_image = _approved(image_asset)
    approved_audio = _approved(audio_asset)
    approved_copy = _approved(copy_asset)

    # The film must be presign-able end to end, which local disk cannot do.
    if approved_image is None or not _presign_possible():
        emit.warning(
            "video_gen",
            "Advertisement Skipped",
            "Multi-shot video needs shot frames that TokenRouter can fetch over "
            "https. Set FERNWOOD_STORAGE=b2 to enable the advertisement track.",
            asset_type="video",
        )
        return None

    visual_description = (
        f"Palette: {approved_image.content.primary_color} dominant, "
        f"{approved_image.content.accent_color} accent. "
        f"{approved_image.critique.reasoning}"
    )
    script = (approved_audio.content.audio_script if approved_audio else "") or ""

    # --- 1. storyboard -------------------------------------------------
    emit.info(
        "video_gen",
        "Writing the Advertisement Storyboard",
        f"Planning a {shot_count}-shot, {shot_count * seconds}s commercial — "
        "hook, product, benefit and close — against the campaign strategy and "
        "the recorded voiceover.",
        asset_type="video",
    )

    shots, sb_manifest = build_storyboard(
        brief,
        campaign_id=campaign_id,
        strategy=strategy,
        voiceover_script=script,
        approved_visual_description=visual_description,
        shot_count=shot_count,
        seconds_per_shot=seconds,
    )
    if not shots:
        shots = fallback_storyboard(brief, shot_count, seconds)
        emit.warning(
            "video_gen",
            "Storyboard Model Unavailable",
            "Falling back to a structural shot list — the advertisement is still "
            "multi-shot, but the scenes are generic rather than written for this brief.",
            asset_type="video",
        )
    else:
        emit.success(
            "video_gen",
            f"Storyboard Written — {len(shots)} Shots",
            " | ".join(f"{_ROLE_LABEL.get(s.role, s.role)}: {s.title}" for s in shots),
            asset_type="video",
        )

    # --- 2 + 3. frames and clips, concurrently -------------------------
    emit.info(
        "video_gen",
        f"Rendering {len(shots)} Shots Concurrently",
        "Each shot gets its own generated first frame and its own camera move. "
        "The video API is a task queue, so the shots are submitted in parallel "
        "rather than one after another.",
        asset_type="video",
    )

    with ThreadPoolExecutor(max_workers=min(4, len(shots))) as pool:
        produced = list(
            pool.map(lambda s: _produce_shot(campaign_id, s, emit), shots)
        )

    shots = [shot for shot, _ in produced]
    clips = [path for _, path in produced if path is not None]

    if not clips:
        emit.error(
            "video_gen",
            "Advertisement Failed",
            "No shot rendered successfully.",
            asset_type="video",
        )
        return None

    # --- 4. cut --------------------------------------------------------
    voiceover_path = _voiceover_file(approved_audio)
    final, has_vo, has_card = _assemble(
        campaign_id,
        brief,
        [s for s in shots if s.status == "rendered"],
        clips,
        voiceover_path,
        approved_copy.content if approved_copy else None,
        emit,
    )
    if final is None:
        emit.error("video_gen", "Advertisement Failed", "Assembly produced nothing.", asset_type="video")
        return None

    duration = assemble.probe_duration(final)
    video_url, manifest_hash = _publish(campaign_id, final)

    rendered = [s for s in shots if s.status == "rendered"]
    attempt = Attempt(
        id=f"att-video-{campaign_id}-1",
        attempt_number=1,
        provider_name=PROVIDER_LABEL,
        model_name=f"{settings.fernwood_video_model} x{len(rendered)} shots",
        prompt_used="\n\n".join(
            f"[{s.index + 1}. {_ROLE_LABEL.get(s.role, s.role)}] {s.title}\n"
            f"  scene:  {s.scene_prompt}\n"
            f"  camera: {s.motion_prompt}"
            for s in rendered
        ),
        timestamp=now_iso(),
        critique_verdict="PASS",
        critique=_critique(rendered, has_vo, has_card, approved_image),
        content=AttemptContent(
            video_url=video_url,
            video_poster_url=rendered[0].frame_url if rendered else None,
            video_duration_seconds=duration,
            ad_shots=shots,
            shot_count=len(rendered),
            has_voiceover=has_vo,
            has_end_card=has_card,
            manifest_hash=manifest_hash,
        ),
    )

    emit.success(
        "video_gen",
        f"Advertisement Complete — {len(rendered)} shots, {duration or '?'}s",
        f"A cut commercial for {brief.brand_name}: "
        + " → ".join(_ROLE_LABEL.get(s.role, s.role) for s in rendered)
        + (" → end card" if has_card else "")
        + (", with voiceover." if has_vo else ", silent."),
        attempt=attempt,
        asset_type="video",
    )

    return Asset(
        id=f"asset-video-{campaign_id}",
        campaign_id=campaign_id,
        type="video",
        attempts=[attempt],
        final_approved_attempt_id=attempt.id,
        status="passed",
    )


def _presign_possible() -> bool:
    from app.storage.backends import LocalDiskBackend
    from app.storage.factory import get_backend

    return not isinstance(get_backend(), LocalDiskBackend)


def _voiceover_file(approved_audio) -> Path | None:
    """Pull the approved voiceover mp3 out of storage for muxing."""
    if approved_audio is None or not approved_audio.content.audio_url:
        return None
    key = _key_from_public_url(approved_audio.content.audio_url)
    if not key:
        return None
    try:
        from app.storage.factory import get_backend

        data = get_backend().get(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not fetch voiceover for mux: %s", exc)
        return None

    path = assemble.workdir("voiceover") / f"{abs(hash(key))}.mp3"
    path.write_bytes(data)
    return path


def _critique(
    rendered: list[AdShot], has_vo: bool, has_card: bool, approved_image
) -> CritiqueResult:
    """Honest record of what was and was not independently scored.

    The shots inherit the approved key visual's art direction, and structural
    completeness is checkable. The MOTION is not scored by any model, and saying
    so plainly is better than implying a rubric that never ran.
    """
    source_score = approved_image.critique.overall_score if approved_image else 90
    structure = int(round(100 * min(1.0, len(rendered) / 3)))

    return CritiqueResult(
        passed=True,
        overall_score=min(source_score, structure),
        criteria=[
            CritiqueCriterion(
                name="Narrative Structure",
                score=structure,
                target_score=100,
                passed=len(rendered) >= 3,
                feedback=(
                    f"{len(rendered)} distinct shots cut in sequence: "
                    + " → ".join(_ROLE_LABEL.get(s.role, s.role) for s in rendered)
                    + "."
                ),
            ),
            CritiqueCriterion(
                name="Campaign Consistency",
                score=source_score,
                target_score=85,
                passed=True,
                feedback=(
                    "Every shot was written against the same strategy and palette as "
                    f"the key visual that passed critique at {source_score}/100."
                ),
            ),
            CritiqueCriterion(
                name="Delivery Completeness",
                score=100 if (has_vo and has_card) else 75 if (has_vo or has_card) else 50,
                target_score=100,
                passed=has_vo and has_card,
                feedback=(
                    f"Voiceover {'laid over the cut' if has_vo else 'absent'}; "
                    f"branded end card {'appended' if has_card else 'absent'}."
                ),
            ),
        ],
        reasoning=(
            f"Assembled advertisement: {len(rendered)} independently generated shots, "
            "each with its own scene and camera move, cut together"
            + (", with the approved voiceover laid across the film" if has_vo else "")
            + (", closing on a branded end card" if has_card else "")
            + ". Shot scenes were written against the campaign strategy and inherit "
            "the approved key visual's palette."
        ),
        suggested_fixes=(
            "The generated MOTION within each shot was not independently scored by a "
            "vision model — only the shot list, the palette lineage and the "
            "structural completeness of the cut were checked."
        ),
    )
