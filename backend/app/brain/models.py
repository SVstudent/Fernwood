"""Campaign Brain wire models.

Same contract discipline as app/domain/models.py: these subclass TSModel, so
they serialize to the camelCase shapes declared in src/types.ts. Changing a
field here means changing that file too.

Two families live in this module and they are deliberately separate:

  * BrainState  — what PERSISTS for a brand, across every campaign it ever ran.
                  Lives at brains/{slug}/brain.json in B2. Versioned.
  * BrainSnapshot — what ONE campaign did with that brain. Embedded in
                  campaign.json so a run stays explicable years later, even if
                  the brain has since learned things that contradict it.

Keeping them apart is what makes the improvement metric trustworthy: a run's
snapshot records the brain as it was AT RUN TIME, so comparing two runs compares
two real historical states rather than one mutable blob read twice.
"""

from __future__ import annotations

from typing import Literal

from app.domain.models import TSModel

LawCategory = Literal["visual", "voice", "copy", "audience", "strategy"]
LawSource = Literal["critique", "audience", "seed"]
LobeId = Literal["recall", "strategy", "foresight", "audience", "learning"]
LobeStatus = Literal["idle", "firing", "done", "skipped"]


class BrandLaw(TSModel):
    """One durable, reusable rule this brand's own failures taught the brain.

    `evidence` is the point of the whole exercise: a law is not an LLM opinion,
    it is a citation. It names the campaign, the attempt and the critique
    sentence that produced it, so a judge (or a brand manager) can click
    straight through to the rejected asset that proves it.
    """

    id: str
    text: str
    category: LawCategory
    source: LawSource
    confidence: int  # 0-100
    evidence: str
    learned_from_campaign_id: str
    learned_from_attempt_id: str | None = None
    learned_at: str
    # Bumped when a later run independently rediscovers the same lesson. A law
    # reinforced three times is worth more than a fresh guess, and this is what
    # ranks the laws fed into the next campaign's prompts.
    reinforced_count: int = 1


class Persona(TSModel):
    """A synthetic member of the brief's target audience.

    Persisted per brand so the same panel reviews every campaign. That is not a
    cosmetic choice: a resonance score is only comparable across runs if the
    judges are held constant.
    """

    id: str
    name: str
    age: int
    occupation: str
    location: str
    mindset: str
    # 0-100. High-skepticism personas are the ones worth listening to; a panel
    # that loves everything measures nothing.
    skepticism: int
    media_diet: str


class PersonaReaction(TSModel):
    persona_id: str
    persona_name: str
    sentiment: int  # 0-100
    verdict: Literal["loves", "likes", "indifferent", "dislikes"]
    # What this person would actually say out loud — the single most useful
    # output of the lobe, and what makes the panel legible at a glance.
    quote: str
    objection: str
    would_act: int  # 0-100, likelihood to click / buy / share
    attention_seconds: float  # how long before they scroll past


class AudienceReport(TSModel):
    personas: list[Persona] = []
    reactions: list[PersonaReaction] = []
    resonance_score: int = 0
    consensus: str = ""
    top_objection: str = ""
    # Population standard deviation of sentiment. High polarization with a good
    # mean is a materially different result from mild universal approval, and
    # an average alone hides it.
    polarization: int = 0
    # Stated plainly because the panel runs on a TEXT model: it reads the copy
    # and script directly, and reads the vision critique's description of the
    # key visual rather than the pixels.
    basis: str = ""


class CampaignStrategy(TSModel):
    big_idea: str
    positioning: str
    visual_direction: str
    voice_direction: str
    copy_angle: str
    avoid: list[str] = []
    laws_applied: list[str] = []  # BrandLaw ids


class Foresight(TSModel):
    """The brain's prediction, made before any generation quota is spent.

    Kept honest by scoring it afterwards: `calibration_error` is the absolute
    gap between prediction and outcome. A brain that cannot predict its own
    output is worth less than one that can, and this makes that measurable
    instead of assumed.
    """

    predicted_score: int
    predicted_retries: int
    likely_failure_mode: str
    confidence: int
    rationale: str = ""
    # Filled in after the run completes.
    actual_score: int | None = None
    actual_retries: int | None = None
    calibration_error: int | None = None


class LearningDelta(TSModel):
    laws_added: list[BrandLaw] = []
    laws_reinforced: list[str] = []
    summary: str = ""
    version_before: int = 0
    version_after: int = 0


class RunRecord(TSModel):
    """One campaign's line in the brain's permanent history.

    This is the substrate of the improvement metric, so it records the
    conditions of the run and not just its results — including
    `forced_first_retry`, which artificially caps the first image critique for
    demo purposes and would otherwise silently depress `first_attempt_avg_score`.
    """

    campaign_id: str
    brand_name: str
    created_at: str
    brain_version_at_run: int
    laws_available: int
    total_attempts: int
    retry_count: int
    # Average critique score of each track's FIRST attempt. The headline
    # learning signal: memory should make the opening shot better, not just
    # make the retries converge.
    first_attempt_avg_score: int
    final_quality_score: int
    resonance_score: int | None = None
    predicted_score: int | None = None
    calibration_error: int | None = None
    forced_first_retry: bool = False


class ImprovementDelta(TSModel):
    """Computed, never stored — the measurable self-improvement panel.

    Compares the brand's FIRST recorded run against its most recent one. All
    fields are derived from RunRecords written at the time of each run, so
    nothing here can drift as the brain keeps learning.
    """

    has_baseline: bool = False
    runs: int = 0
    baseline: RunRecord | None = None
    latest: RunRecord | None = None
    first_attempt_score_delta: int = 0
    retry_delta: int = 0  # negative is better — fewer retries
    quality_delta: int = 0
    resonance_delta: int | None = None
    laws_delta: int = 0
    summary: str = ""
    # Set when the two runs were not measured under the same conditions, so the
    # UI can disclose it rather than overstate the gain.
    caveat: str = ""


class BrainState(TSModel):
    """The persistent brain for one brand. brains/{slug}/brain.json."""

    brand_slug: str
    brand_name: str
    version: int = 0
    created_at: str = ""
    updated_at: str = ""
    laws: list[BrandLaw] = []
    personas: list[Persona] = []
    history: list[RunRecord] = []
    lifetime_campaigns: int = 0


class BrainSnapshot(TSModel):
    """What one campaign's brain did. Embedded in campaign.json."""

    brand_slug: str
    brand_name: str = ""
    cold_start: bool = True
    brain_version_before: int = 0
    brain_version_after: int = 0
    laws_applied: list[BrandLaw] = []
    strategy: CampaignStrategy | None = None
    foresight: Foresight | None = None
    audience: AudienceReport | None = None
    learning: LearningDelta | None = None
    improvement: ImprovementDelta | None = None
    lobes: dict[str, str] = {}
    # Manifest hashes for each lobe's inference call. The brain's own reasoning
    # is provenance-tracked on the same footing as the assets it directs.
    lobe_manifests: dict[str, str] = {}
    model_used: str = ""
