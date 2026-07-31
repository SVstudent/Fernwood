"""Campaign lifecycle endpoints."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.domain.models import CampaignBrief
from app.pipeline.orchestrator import draft_campaign, new_campaign_id, run_campaign
from app.runtime.registry import REGISTRY
from app.storage import index

logger = logging.getLogger(__name__)
router = APIRouter(tags=["campaigns"])


@router.post("/campaigns", status_code=202)
async def start_campaign(brief: CampaignBrief) -> dict:
    """Start a run and return immediately.

    POST-then-SSE-GET rather than streaming this response: a run takes minutes,
    browser EventSource cannot POST, and a separate GET stream is re-openable
    after a tab reload.
    """
    campaign_id = new_campaign_id()
    campaign = draft_campaign(campaign_id, brief)
    REGISTRY.create(campaign_id)

    # The pipeline is sync/blocking (genblaze is a sync SDK), so it runs in a
    # worker thread and publishes progress via the registry.
    asyncio.create_task(asyncio.to_thread(run_campaign, campaign, brief))

    return {
        "campaignId": campaign_id,
        "streamUrl": f"/api/campaigns/{campaign_id}/stream",
        "campaign": campaign.ts(),
    }


@router.get("/campaigns")
async def list_campaigns() -> dict:
    campaigns, source = await asyncio.to_thread(index.list_campaigns)
    return {"campaigns": campaigns, "source": source}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str) -> dict:
    data = await asyncio.to_thread(index.get_campaign, campaign_id)
    if data is None:
        run = REGISTRY.get(campaign_id)
        if run and run.campaign:
            return run.campaign
        raise HTTPException(status_code=404, detail="Campaign not found")
    return data


@router.delete("/campaigns/{campaign_id}", status_code=204)
async def delete_campaign(campaign_id: str) -> None:
    await asyncio.to_thread(index.delete_campaign, campaign_id)


@router.post("/admin/reindex")
async def reindex() -> dict:
    """Self-heal the Library rollup by scanning storage."""
    found = await asyncio.to_thread(index.rebuild_index)
    return {"campaigns": len(found)}
