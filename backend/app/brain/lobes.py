"""The five lobes.

Every function here obeys the same contract: it returns its best result and a
manifest hash, it never raises, and a failure returns None so the caller can
mark that lobe 'skipped' and carry on. The campaign pipeline predates the brain
and must remain able to complete without it.
"""

from __future__ import annotations

import logging
import statistics
from typing import Any

from app.brain.llm import brain_call, clamp
from app.brain.models import (
    AudienceReport,
    BrainState,
    BrandLaw,
    CampaignStrategy,
    Foresight,
    LearningDelta,
    Persona,
    PersonaReaction,
)
from app.brain.prompts import (
    foresight_prompt,
    learning_prompt,
    personas_prompt,
    reactions_prompt,
    rejection_block,
    strategy_prompt,
)
from app.brain.schemas import (
    FORESIGHT_SCHEMA,
    LEARNING_SCHEMA,
    PERSONAS_SCHEMA,
    REACTIONS_SCHEMA,
    STRATEGY_SCHEMA,
)
from app.brain.store import now_iso, top_laws
from app.config import get_settings
from app.domain.models import Campaign, CampaignBrief

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = {"visual", "voice", "copy", "audience", "strategy"}
_VALID_VERDICTS = {"loves", "likes", "indifferent", "dislikes"}


# ------------------------------------------------------------------- RECALL
def recall(brain: BrainState) -> list[BrandLaw]:
    """Surface the laws this brand's past failures earned.

    No inference call — recall is a storage read by design. The intelligence was
    spent when the laws were written; retrieving them should be free and
    deterministic, and a lobe that re-derives its memory every run is not
    memory.
    """
    return top_laws(brain)


def history_note(brain: BrainState) -> str:
    """A compact record of past runs, for the Foresight lobe to calibrate on."""
    if not brain.history:
        return "PRIOR RUNS: none. This is the first campaign for this brand."
    lines = ["PRIOR RUNS FOR THIS BRAND:"]
    for record in brain.history[-5:]:
        lines.append(
            f"  {record.campaign_id}: first attempts averaged "
            f"{record.first_attempt_avg_score}/100, {record.retry_count} retries, "
            f"final quality {record.final_quality_score}/100"
            + (
                f", audience resonance {record.resonance_score}/100"
                if record.resonance_score is not None
                else ""
            )
        )
    return "\n".join(lines)


# ----------------------------------------------------------------- STRATEGY
def strategize(
    brief: CampaignBrief, laws: list[BrandLaw], campaign_id: str
) -> tuple[CampaignStrategy | None, str | None]:
    parsed, manifest = brain_call(
        "strategy",
        campaign_id=campaign_id,
        prompt=strategy_prompt(brief, laws),
        schema=STRATEGY_SCHEMA,
        temperature=0.75,
    )
    if not parsed:
        return None, None

    avoid = [str(x).strip() for x in (parsed.get("avoid") or []) if str(x).strip()]
    strategy = CampaignStrategy(
        big_idea=str(parsed.get("bigIdea") or "").strip(),
        positioning=str(parsed.get("positioning") or "").strip(),
        visual_direction=str(parsed.get("visualDirection") or "").strip(),
        voice_direction=str(parsed.get("voiceDirection") or "").strip(),
        copy_angle=str(parsed.get("copyAngle") or "").strip(),
        avoid=avoid[:6],
        laws_applied=[law.id for law in laws],
    )
    # A strategy with no big idea is not a strategy; better to skip the lobe
    # than to inject an empty directive into every downstream prompt.
    if not strategy.big_idea:
        return None, manifest
    return strategy, manifest


# ---------------------------------------------------------------- FORESIGHT
def foresee(
    brief: CampaignBrief,
    laws: list[BrandLaw],
    strategy: CampaignStrategy | None,
    brain: BrainState,
    campaign_id: str,
) -> tuple[Foresight | None, str | None]:
    settings = get_settings()
    parsed, manifest = brain_call(
        "foresight",
        campaign_id=campaign_id,
        prompt=foresight_prompt(
            brief,
            laws,
            strategy,
            history_note(brain),
            settings.fernwood_pass_threshold,
        ),
        schema=FORESIGHT_SCHEMA,
        temperature=0.4,  # a prediction should not be creative
        max_tokens=700,
    )
    if not parsed:
        return None, None

    return (
        Foresight(
            predicted_score=clamp(parsed.get("predictedScore"), default=75),
            predicted_retries=clamp(parsed.get("predictedRetries"), 0, 6, default=1),
            likely_failure_mode=str(parsed.get("likelyFailureMode") or "").strip()
            or "No specific failure mode predicted.",
            confidence=clamp(parsed.get("confidence"), default=50),
            rationale=str(parsed.get("rationale") or "").strip(),
        ),
        manifest,
    )


def score_foresight(foresight: Foresight, campaign: Campaign) -> Foresight:
    """Grade the prediction against what actually happened.

    Calibration is measured on the FINAL quality score because that is the
    number the prediction named. Recorded even when it is embarrassing — a
    calibration metric you only publish when it flatters you is decoration.
    """
    foresight.actual_score = campaign.overall_quality_score
    foresight.actual_retries = campaign.retry_count
    foresight.calibration_error = abs(
        foresight.predicted_score - campaign.overall_quality_score
    )
    return foresight


# ----------------------------------------------------------------- AUDIENCE
def build_personas(
    brief: CampaignBrief, brain: BrainState, campaign_id: str
) -> tuple[list[Persona], str | None]:
    """Reuse this brand's existing panel, or convene one.

    Personas are persisted deliberately. Resonance is only comparable between
    campaign #1 and campaign #5 if the same people scored both; regenerating the
    panel each run would make every cross-run comparison meaningless.
    """
    if brain.personas:
        return brain.personas, None

    parsed, manifest = brain_call(
        "audience",
        campaign_id=campaign_id,
        prompt=personas_prompt(brief),
        schema=PERSONAS_SCHEMA,
        temperature=0.9,  # the panel needs genuine spread
    )
    if not parsed:
        return [], None

    personas: list[Persona] = []
    for i, raw in enumerate(parsed.get("personas") or []):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or f"Panelist {i + 1}").strip()
        personas.append(
            Persona(
                id=f"persona-{brain.brand_slug}-{i + 1}",
                name=name,
                age=clamp(raw.get("age"), 13, 95, default=35),
                occupation=str(raw.get("occupation") or "Unspecified").strip(),
                location=str(raw.get("location") or "Unspecified").strip(),
                mindset=str(raw.get("mindset") or "").strip(),
                skepticism=clamp(raw.get("skepticism"), default=50),
                media_diet=str(raw.get("mediaDiet") or "").strip(),
            )
        )
    return personas, manifest


def _visual_description(campaign: Campaign) -> str:
    """What the panel is told about the key visual.

    The panel runs on a TEXT model, so it cannot see the image. Rather than
    pretend otherwise, it is handed the vision critique's own written assessment
    of the approved frame — a real description produced by a model that did look
    at the pixels. AudienceReport.basis states this on the record.
    """
    asset = campaign.assets.image
    if not asset or not asset.attempts:
        return "No key visual was produced for this campaign."
    approved = next(
        (a for a in asset.attempts if a.id == asset.final_approved_attempt_id),
        max(asset.attempts, key=lambda a: a.critique.overall_score),
    )
    palette = (
        f"Palette: primary {approved.content.primary_color}, "
        f"secondary {approved.content.secondary_color}, "
        f"accent {approved.content.accent_color}. "
    )
    return (
        palette
        + f"Vision critique ({approved.critique.overall_score}/100): "
        + approved.critique.reasoning
    )


def simulate_audience(
    brief: CampaignBrief,
    personas: list[Persona],
    campaign: Campaign,
    campaign_id: str,
) -> tuple[AudienceReport | None, str | None]:
    if not personas:
        return None, None

    parsed, manifest = brain_call(
        "audience_reaction",
        campaign_id=campaign_id,
        prompt=reactions_prompt(brief, personas, campaign, _visual_description(campaign)),
        schema=REACTIONS_SCHEMA,
        temperature=0.85,
        max_tokens=2000,
    )
    if not parsed:
        return None, None

    by_name = {p.name.lower(): p for p in personas}
    reactions: list[PersonaReaction] = []
    for raw in parsed.get("reactions") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("personaName") or "").strip()
        persona = by_name.get(name.lower())
        # Positional fallback: models occasionally paraphrase the name back
        # ("Maya R." for "Maya Rodriguez"), and dropping the reaction over a
        # string mismatch would silently shrink the panel.
        if persona is None and len(reactions) < len(personas):
            persona = personas[len(reactions)]
        if persona is None:
            continue

        verdict = str(raw.get("verdict") or "").strip().lower()
        reactions.append(
            PersonaReaction(
                persona_id=persona.id,
                persona_name=persona.name,
                sentiment=clamp(raw.get("sentiment"), default=50),
                verdict=verdict if verdict in _VALID_VERDICTS else "indifferent",  # type: ignore[arg-type]
                quote=str(raw.get("quote") or "").strip(),
                objection=str(raw.get("objection") or "").strip(),
                would_act=clamp(raw.get("wouldAct"), default=40),
                attention_seconds=_attention(raw.get("attentionSeconds")),
            )
        )

    if not reactions:
        return None, manifest

    return (
        AudienceReport(
            personas=personas,
            reactions=reactions,
            resonance_score=_resonance(reactions),
            consensus=str(parsed.get("consensus") or "").strip(),
            top_objection=str(parsed.get("topObjection") or "").strip(),
            polarization=_polarization(reactions),
            basis=(
                "Simulated panel. Reactions are generated by a text model that read "
                "the copy and voiceover script verbatim, and read the vision model's "
                "written critique of the key visual rather than the image itself. "
                "This is directional signal, not fielded market research."
            ),
        ),
        manifest,
    )


def _attention(value: Any) -> float:
    try:
        return round(max(0.0, min(60.0, float(value))), 1)
    except (TypeError, ValueError):
        return 1.5


def _resonance(reactions: list[PersonaReaction]) -> int:
    """Weighted blend of felt sentiment and stated intent to act.

    Intent is weighted at 40% rather than averaged in equally: an audience that
    admires an ad without acting on it is a real and common outcome, and a
    single figure that cannot distinguish the two would flatter every campaign.
    """
    sentiment = statistics.fmean(r.sentiment for r in reactions)
    intent = statistics.fmean(r.would_act for r in reactions)
    return int(round(0.6 * sentiment + 0.4 * intent))


def _polarization(reactions: list[PersonaReaction]) -> int:
    """Population standard deviation of sentiment.

    Reported alongside the mean because they mean different things: 50/100 from
    a panel that mildly shrugged is a fixable brief, while 50/100 from two
    people who loved it and two who hated it is a positioning decision.
    """
    if len(reactions) < 2:
        return 0
    return int(round(statistics.pstdev([r.sentiment for r in reactions])))


# ----------------------------------------------------------------- LEARNING
def learn(
    brief: CampaignBrief,
    campaign: Campaign,
    brain: BrainState,
    audience: AudienceReport | None,
    campaign_id: str,
) -> tuple[LearningDelta | None, str | None]:
    """Distil durable laws from this run's rejections and audience objections."""
    audience_block = "No audience panel ran for this campaign."
    if audience and audience.reactions:
        lines = [
            f"Resonance {audience.resonance_score}/100 "
            f"(polarization {audience.polarization}). "
            f"Consensus: {audience.consensus} Top objection: {audience.top_objection}"
        ]
        for reaction in audience.reactions:
            lines.append(
                f'  {reaction.persona_name} ({reaction.verdict}, sentiment '
                f'{reaction.sentiment}, would act {reaction.would_act}): '
                f'"{reaction.quote}" — objection: {reaction.objection}'
            )
        audience_block = "\n".join(lines)

    existing = top_laws(brain)
    parsed, manifest = brain_call(
        "learning",
        campaign_id=campaign_id,
        prompt=learning_prompt(
            brief, campaign, existing, rejection_block(campaign), audience_block
        ),
        schema=LEARNING_SCHEMA,
        temperature=0.5,
    )
    if not parsed:
        return None, None

    known_ids = {law.id for law in brain.laws}
    existing_texts = {law.text.strip().lower() for law in brain.laws}

    new_laws: list[BrandLaw] = []
    for i, raw in enumerate(parsed.get("newLaws") or []):
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        # A law with no evidence is an opinion. The whole value of this store is
        # that every entry cites the run that earned it, so unsourced entries
        # are dropped rather than saved with a placeholder.
        evidence = str(raw.get("evidence") or "").strip()
        if not text or not evidence or text.lower() in existing_texts:
            continue
        category = str(raw.get("category") or "strategy").strip().lower()
        new_laws.append(
            BrandLaw(
                id=f"law-{campaign_id}-{i + 1}",
                text=text,
                category=category if category in _VALID_CATEGORIES else "strategy",  # type: ignore[arg-type]
                source="audience" if "objection" in evidence.lower() else "critique",
                confidence=clamp(raw.get("confidence"), default=60),
                evidence=evidence,
                learned_from_campaign_id=campaign_id,
                learned_at=now_iso(),
            )
        )
        existing_texts.add(text.lower())

    reinforced = [
        str(x) for x in (parsed.get("reinforcedLawIds") or []) if str(x) in known_ids
    ]

    return (
        LearningDelta(
            laws_added=new_laws,
            laws_reinforced=reinforced,
            summary=str(parsed.get("summary") or "").strip(),
            version_before=brain.version,
            version_after=brain.version + 1,
        ),
        manifest,
    )


def apply_learning(brain: BrainState, delta: LearningDelta) -> BrainState:
    """Fold a LearningDelta into the persistent brain and bump its version."""
    by_id = {law.id: law for law in brain.laws}
    for law_id in delta.laws_reinforced:
        law = by_id.get(law_id)
        if law is None:
            continue
        law.reinforced_count += 1
        # Reinforcement raises confidence with a ceiling: repeated agreement is
        # evidence, but a law that never had a counter-example is not certain.
        law.confidence = min(99, law.confidence + 5)

    brain.laws.extend(delta.laws_added)
    brain.version = delta.version_after
    return brain
