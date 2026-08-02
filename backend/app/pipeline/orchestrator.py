"""Campaign orchestration — the real replacement for the mock
executeFullCampaignPipeline(). Runs in a worker thread; publishes progress
through the registry so the SSE endpoint can stream it."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.domain.models import Campaign, CampaignAssets, CampaignBrief
from app.config import get_settings
from app.pipeline.tracks import run_track, run_video_track
from app.runtime.logbus import Emitter, now_iso
from app.storage.index import save_campaign

logger = logging.getLogger(__name__)


def new_campaign_id() -> str:
    return f"camp-{int(datetime.now(UTC).timestamp() * 1000)}"


def draft_campaign(campaign_id: str, brief: CampaignBrief) -> Campaign:
    ts = now_iso()
    return Campaign(
        id=campaign_id,
        brand_name=brief.brand_name,
        product_service=brief.product_service,
        target_audience=brief.target_audience,
        brief_text=brief.brief_text,
        tone_tags=brief.tone_tags,
        colors=brief.colors,
        created_at=ts,
        updated_at=ts,
        status="running",
        assets=CampaignAssets(),
    )


def _embed_provenance(campaign: Campaign, emit: Emitter) -> None:
    """Write each asset's manifest into the delivered media file itself.

    A downloaded MP4/JPEG/MP3 then carries its own verifiable generation history
    — extractable without B2 or this service. Best-effort: a container that
    rejects the metadata block must never fail a completed campaign.
    """
    from genblaze_core import Manifest

    from app.pipeline.embed import embed_into_delivery
    from app.storage.factory import get_backend

    backend = get_backend()
    plan = [
        ("image", campaign.assets.image, "image_url", "image/jpeg"),
        ("audio", campaign.assets.audio, "audio_url", "audio/mpeg"),
        ("video", campaign.assets.video, "video_url", "video/mp4"),
    ]

    embedded: list[str] = []
    for kind, asset, url_field, media_type in plan:
        if asset is None or not asset.attempts:
            continue
        approved = next(
            (a for a in asset.attempts if a.id == asset.final_approved_attempt_id),
            asset.attempts[-1],
        )
        public_url = getattr(approved.content, url_field, None)
        manifest_url = approved.content.manifest_uri
        if not public_url or not manifest_url:
            continue

        source_key = public_url.removeprefix("/api/media/")
        manifest_key = manifest_url.removeprefix("/api/media/")
        try:
            manifest = Manifest.model_validate_json(backend.get(manifest_key))
        except Exception as exc:  # noqa: BLE001
            logger.warning("no manifest for %s embed: %s", kind, exc)
            continue

        # JPEG vs PNG matters to the handler registry.
        if kind == "image" and source_key.lower().endswith(".png"):
            media_type = "image/png"

        key = embed_into_delivery(
            campaign_id=campaign.id,
            asset_kind=kind,
            source_key=source_key,
            manifest=manifest,
            media_type=media_type,
        )
        if key:
            campaign.delivery[kind] = f"/api/media/{key}"
            embedded.append(kind)

    if embedded:
        emit.success(
            "b2_upload",
            "Provenance Embedded in Media",
            f"SHA-256 manifest written into the delivered {', '.join(embedded)} "
            "file(s) — each asset now carries its own verifiable audit trail.",
        )


def run_campaign(campaign: Campaign, brief: CampaignBrief) -> Campaign:
    """Execute all three tracks sequentially. Never raises — failures are
    reported as error frames and the campaign is marked failed."""
    emit = Emitter(campaign.id)

    try:
        emit.campaign(campaign)
        emit.info(
            "brief_analysis",
            "Analyzing Brand Brief",
            f'Parsing brand guidelines for "{brief.brand_name}". '
            f"Target tone: {', '.join(brief.tone_tags) or 'Modern'}.",
        )

        for asset_type in ("image", "audio", "copy"):
            asset = run_track(asset_type, brief, campaign.id, emit)
            setattr(campaign.assets, asset_type, asset)
            campaign.total_attempts_count += len(asset.attempts)
            campaign.retry_count += max(0, len(asset.attempts) - 1)
            campaign.updated_at = now_iso()
            emit.campaign(campaign)

        # Video runs last and only on request: it is derived from the approved
        # key visual, and it adds ~2 minutes plus real quota per campaign.
        settings = get_settings()
        if brief.include_video and settings.fernwood_enable_video:
            video_asset = run_video_track(brief, campaign.id, emit, campaign.assets.image)
            if video_asset is not None:
                campaign.assets.video = video_asset
                campaign.total_attempts_count += len(video_asset.attempts)
                campaign.updated_at = now_iso()
                emit.campaign(campaign)

        emit.info(
            "assembly",
            "Assembling Campaign Kit",
            "Compiling approved visual, audio, and copywriting assets into provenance record...",
        )

        emit.info(
            "b2_upload",
            "Persisting to Backblaze B2",
            "Uploading asset binaries and provenance audit log to Backblaze B2 bucket...",
        )
        save_campaign(campaign)

        if settings.fernwood_embed_provenance:
            _embed_provenance(campaign, emit)

        approved_scores = []
        for asset_type in ("image", "audio", "copy"):
            asset = getattr(campaign.assets, asset_type)
            if asset and asset.attempts:
                best = max(a.critique.overall_score for a in asset.attempts)
                approved_scores.append(best)

        campaign.overall_quality_score = (
            int(round(sum(approved_scores) / len(approved_scores))) if approved_scores else 0
        )

        # A campaign is "failed" only when an asset could not be PRODUCED at all
        # (provider outage, zero attempts). An asset that generated fine but
        # never cleared the critique threshold still yields a usable kit — its
        # own status stays 'failed' and every rejected attempt remains visible
        # in the provenance log, so nothing is hidden. Marking the whole
        # campaign failed for a strict quality bar would misreport a run that
        # actually delivered all three assets.
        produced_nothing = any(
            (asset := getattr(campaign.assets, t)) is None or not asset.attempts
            for t in ("image", "audio", "copy")
        )
        campaign.status = "failed" if produced_nothing else "completed"
        campaign.updated_at = now_iso()
        save_campaign(campaign)

        emit.success(
            "assembly",
            "Pipeline Complete",
            f'Campaign Kit for "{brief.brand_name}" finalized with overall quality '
            f"score of {campaign.overall_quality_score}/100!",
        )
        emit.done(campaign)
        return campaign

    except Exception as exc:  # noqa: BLE001
        logger.exception("Campaign %s failed", campaign.id)
        campaign.status = "failed"
        campaign.updated_at = now_iso()
        try:
            save_campaign(campaign)
        except Exception:  # noqa: BLE001
            pass
        emit.fatal("assembly", str(exc))
        return campaign
