"""The measurable self-improvement metric.

This is the claim the whole feature stands on — "the brain gets better at this
brand" — so the arithmetic lives in one small, testable module rather than
being scattered through the orchestrator.

Design rules that keep the number honest:

  * Compare RUN RECORDS, not live state. Each record was written at the time of
    its run, so a later brain cannot retroactively improve an earlier score.
  * The headline signal is FIRST-ATTEMPT quality, not final quality. The retry
    loop already drags almost everything over the line eventually; what memory
    should change is how good the opening shot is before any critique fires.
  * Disclose contamination instead of hiding it. FERNWOOD_FORCE_FIRST_RETRY
    caps the first image critique for demo purposes, so runs made under
    different settings are flagged with a caveat rather than silently compared.
  * Never fabricate a trend. One run is a baseline, not an improvement, and
    that is what the panel says.
"""

from __future__ import annotations

from app.brain.models import BrainState, ImprovementDelta, RunRecord
from app.domain.models import Campaign

_TRACKS = ("image", "audio", "copy")


def first_attempt_scores(campaign: Campaign) -> list[int]:
    """Critique score of each track's FIRST attempt.

    Prefers `pre_cap_score` where present: FERNWOOD_FORCE_FIRST_RETRY rewrites
    the first image critique down to force a visible retry, and scoring the
    brain against a number the demo harness chose would measure nothing.
    """
    scores: list[int] = []
    for track in _TRACKS:
        asset = getattr(campaign.assets, track, None)
        if not asset or not asset.attempts:
            continue
        first = min(asset.attempts, key=lambda a: a.attempt_number)
        critique = first.critique
        scores.append(critique.pre_cap_score or critique.overall_score)
    return scores


def build_run_record(
    campaign: Campaign,
    *,
    brain: BrainState,
    version_at_run: int,
    laws_available: int,
    resonance_score: int | None,
    predicted_score: int | None,
    calibration_error: int | None,
    forced_first_retry: bool,
) -> RunRecord:
    """Freeze this campaign's outcome into the brain's permanent history.

    `version_at_run` is passed in rather than read from `brain.version`: by the
    time this is called the Learning lobe has already bumped the live brain, so
    reading it here would credit the run with knowledge it did not have.
    """
    scores = first_attempt_scores(campaign)
    return RunRecord(
        campaign_id=campaign.id,
        brand_name=campaign.brand_name,
        created_at=campaign.created_at,
        brain_version_at_run=version_at_run,
        laws_available=laws_available,
        total_attempts=campaign.total_attempts_count,
        retry_count=campaign.retry_count,
        first_attempt_avg_score=int(round(sum(scores) / len(scores))) if scores else 0,
        final_quality_score=campaign.overall_quality_score,
        resonance_score=resonance_score,
        predicted_score=predicted_score,
        calibration_error=calibration_error,
        forced_first_retry=forced_first_retry,
    )


def compute_improvement(brain: BrainState) -> ImprovementDelta:
    """Compare the brand's first recorded run against its most recent one."""
    history = list(brain.history)

    if not history:
        return ImprovementDelta(
            has_baseline=False,
            runs=0,
            summary=(
                f"No campaigns recorded for {brain.brand_name} yet. The first run "
                "establishes the baseline this brain will be measured against."
            ),
        )

    if len(history) == 1:
        return ImprovementDelta(
            has_baseline=False,
            runs=1,
            baseline=history[0],
            latest=history[0],
            laws_delta=len(brain.laws),
            summary=(
                f"Baseline recorded: first attempts averaged "
                f"{history[0].first_attempt_avg_score}/100 across "
                f"{history[0].retry_count} retries, with no prior memory to draw on. "
                f"The brain has since written {len(brain.laws)} brand "
                f"{'law' if len(brain.laws) == 1 else 'laws'}. Run this brief again "
                "to measure what they are worth."
            ),
        )

    baseline, latest = history[0], history[-1]

    first_delta = latest.first_attempt_avg_score - baseline.first_attempt_avg_score
    retry_delta = latest.retry_count - baseline.retry_count
    quality_delta = latest.final_quality_score - baseline.final_quality_score
    resonance_delta = (
        latest.resonance_score - baseline.resonance_score
        if latest.resonance_score is not None and baseline.resonance_score is not None
        else None
    )

    caveat = ""
    if baseline.forced_first_retry != latest.forced_first_retry:
        caveat = (
            "These two runs used different FERNWOOD_FORCE_FIRST_RETRY settings, "
            "which caps the first image critique. The first-attempt comparison "
            "is not like-for-like."
        )

    return ImprovementDelta(
        has_baseline=True,
        runs=len(history),
        baseline=baseline,
        latest=latest,
        first_attempt_score_delta=first_delta,
        retry_delta=retry_delta,
        quality_delta=quality_delta,
        resonance_delta=resonance_delta,
        laws_delta=latest.laws_available - baseline.laws_available,
        summary=_summarize(brain, baseline, latest, first_delta, retry_delta),
        caveat=caveat,
    )


def _summarize(
    brain: BrainState,
    baseline: RunRecord,
    latest: RunRecord,
    first_delta: int,
    retry_delta: int,
) -> str:
    """One plain sentence a judge can read off the screen in three seconds."""
    laws = latest.laws_available
    stem = (
        f"Across {len(brain.history)} campaigns for {brain.brand_name}, the brain went "
        f"from {baseline.laws_available} learned laws to {laws}. "
    )

    if first_delta > 0 and retry_delta < 0:
        return (
            stem + f"First-attempt quality rose {first_delta} points "
            f"({baseline.first_attempt_avg_score} to {latest.first_attempt_avg_score}) "
            f"while retries fell by {abs(retry_delta)} — it is getting the work right "
            "sooner, not just fixing it faster."
        )
    if first_delta > 0:
        return (
            stem + f"First-attempt quality rose {first_delta} points "
            f"({baseline.first_attempt_avg_score} to {latest.first_attempt_avg_score}). "
            "Retries held steady."
        )
    if retry_delta < 0:
        return (
            stem + f"Retries fell by {abs(retry_delta)}, though first-attempt scores "
            "have not separated yet."
        )
    if first_delta == 0 and retry_delta == 0:
        return stem + "Neither first-attempt quality nor retry count has moved yet."
    return (
        stem + f"This run scored {abs(first_delta)} points "
        f"{'below' if first_delta < 0 else 'above'} the baseline on first attempts — "
        "generation is stochastic, and a single run either way is noise rather than "
        "a trend."
    )
