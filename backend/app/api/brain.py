"""Campaign Brain endpoints.

Read-only apart from the reset, which exists for one specific reason: the
headline demo is "run the same brief cold, then run it again warm", and that
needs a supported way to put a brand back to zero. Doing it by hand in the B2
console mid-presentation is not a plan.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.brain.metrics import compute_improvement
from app.brain.models import BrainState
from app.brain.store import brand_slug, delete_brain, list_brains, load_brain
from app.config import Resolved, get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["brain"])


def _payload(brain: BrainState) -> dict:
    """A brain plus its derived improvement panel.

    `improvement` is computed on read rather than stored, so it can never drift
    out of sync with the history it summarizes.
    """
    return {
        "brain": brain.ts(),
        "improvement": compute_improvement(brain).ts(),
        "model": Resolved.text_model,
    }


@router.get("/brains")
async def brains() -> dict:
    """Every brand brain in storage, newest first."""
    found = await asyncio.to_thread(list_brains)
    return {"brains": found, "count": len(found)}


@router.get("/brain/{slug}")
async def get_brain(slug: str) -> dict:
    """One brand's brain by slug.

    load_brain() takes a brand NAME and slugifies it; slugifying an
    already-slugged string is a no-op, so passing the slug straight through is
    safe and keeps this endpoint symmetric with the storage layout.
    """
    brain = await asyncio.to_thread(load_brain, slug)
    if brain.version == 0 and not brain.laws and not brain.history:
        raise HTTPException(status_code=404, detail="No brain for that brand yet")
    return _payload(brain)


@router.get("/brain/by-brand/{brand_name}")
async def get_brain_by_brand(brand_name: str) -> dict:
    """Look a brain up by human brand name.

    Returns an empty brain with 200 rather than 404: the brief form uses this to
    show "this brand has no memory yet" while the user is still typing, and a
    404 for the normal cold-start case would be noise in the console.
    """
    brain = await asyncio.to_thread(load_brain, brand_name)
    return {**_payload(brain), "slug": brand_slug(brand_name)}


@router.delete("/brain/{slug}", status_code=204)
async def reset_brain(slug: str) -> None:
    """Wipe a brand's learned memory so the next run is a true cold start.

    Versioned snapshots under brains/{slug}/v{n}.json survive — a reset gives a
    clean baseline, it does not erase the evidence behind past claims.
    """
    if not get_settings().fernwood_enable_brain:
        raise HTTPException(status_code=409, detail="Campaign Brain is disabled")
    await asyncio.to_thread(delete_brain, slug)
