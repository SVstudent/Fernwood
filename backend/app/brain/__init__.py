"""The Campaign Brain — a persistent, per-brand intelligence layer.

Fernwood already generates every rejected attempt AND the structured critique
that rejected it, then stores both in B2 forever. Until now that archive was
write-only: campaign #7 for a brand started from exactly the same blank slate as
campaign #1, and re-made the same mistakes.

The Brain reads that archive back. It distils durable *brand laws* from past
failures, uses them to aim the next campaign before a single image is
generated, simulates how the brief's actual target audience reacts to the
result, and writes what it learned back to storage — versioned, with each law
carrying provenance to the exact campaign and critique that taught it.

Five lobes, each a real inference call on the free Kimi tier:

    RECALL     load this brand's accumulated laws from B2
    STRATEGY   brief + laws -> one campaign strategy the tracks must follow
    FORESIGHT  predict the score and failure mode BEFORE spending any quota
    AUDIENCE   synthetic personas from the brief react to the finished work
    LEARNING   distil new laws from this run's rejections and objections

Everything here is best-effort by construction. A brain lobe that fails must
degrade to "skipped" and let the campaign proceed exactly as it did before this
module existed — the pipeline is the product, the brain is the multiplier.
"""

from app.brain.models import (
    AudienceReport,
    BrainSnapshot,
    BrainState,
    BrandLaw,
    CampaignStrategy,
    Foresight,
    ImprovementDelta,
    LearningDelta,
    Persona,
    PersonaReaction,
    RunRecord,
)

__all__ = [
    "AudienceReport",
    "BrainSnapshot",
    "BrainState",
    "BrandLaw",
    "CampaignStrategy",
    "Foresight",
    "ImprovementDelta",
    "LearningDelta",
    "Persona",
    "PersonaReaction",
    "RunRecord",
]
