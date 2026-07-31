"""Campaign orchestration — the real replacement for the mock
executeFullCampaignPipeline(). Runs in a worker thread; publishes progress
through the registry so the SSE endpoint can stream it."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.domain.models import Campaign, CampaignAssets, CampaignBrief
from app.pipeline.tracks import run_track
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

        approved_scores = []
        for asset_type in ("image", "audio", "copy"):
            asset = getattr(campaign.assets, asset_type)
            if asset and asset.attempts:
                best = max(a.critique.overall_score for a in asset.attempts)
                approved_scores.append(best)

        campaign.overall_quality_score = (
            int(round(sum(approved_scores) / len(approved_scores))) if approved_scores else 0
        )
        any_failed = any(
            getattr(campaign.assets, t) and getattr(campaign.assets, t).status == "failed"
            for t in ("image", "audio", "copy")
        )
        campaign.status = "failed" if any_failed else "completed"
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
