"""Live Campaign Brain tests — real inference, real B2 writes.

    uv run pytest tests/test_live_brain.py -m live -v

Skipped by default. These exist because the offline suite stubs `brain_call`,
which is exactly where the expensive surprises live. Three have already bitten:

  * A Foresight response truncated mid-string at 700 max_tokens, producing
    unparseable JSON that looks identical to the model being unavailable.
  * SDK-level retries multiplied every slow call before the caller's
    response_format ladder multiplied it again, so one lobe could stall for
    minutes and then report nothing.
  * A free-tier model capped at 8 requests/minute silently 429'd every lobe.
    That model is no longer the default, but the pacing that survived it still
    guards anyone who pins one.

None of these is visible without calling the real thing.

The lobes are driven against a synthetic completed campaign rather than a full
pipeline run, so these exercise every real inference call and B2 write without
spending image or video generation quota.
"""

from __future__ import annotations

import pytest

from app.brain import lobes
from app.brain.metrics import build_run_record, compute_improvement
from app.brain.store import brand_slug, load_brain, save_brain
from app.config import Resolved, get_settings
from app.domain.models import (
    Asset,
    Attempt,
    AttemptContent,
    Campaign,
    CampaignAssets,
    CampaignBrief,
    ColorPreference,
    CritiqueResult,
)
from app.providers.client import probe_models

pytestmark = pytest.mark.live

needs_tokenrouter = pytest.mark.skipif(
    not get_settings().has_tokenrouter, reason="TOKENROUTER_API_KEY not set"
)

BRAND = "Fernwood Live Test Coffee"


@pytest.fixture(scope="module")
def resolved():
    probe_models()
    return Resolved


@pytest.fixture(scope="module")
def brief():
    return CampaignBrief(
        brand_name=BRAND,
        product_service="single-origin coffee subscription",
        target_audience="urban professionals aged 28-45 who resent hustle culture",
        brief_text="warm, unhurried, anti-hustle",
        tone_tags=["Cozy & Warm"],
        colors=ColorPreference(primary="#1E3A2B", secondary="#F4F1EA", accent="#D97706"),
    )


def _crit(score: int, passed: bool, reasoning: str, fixes: str) -> CritiqueResult:
    return CritiqueResult(
        passed=passed,
        overall_score=score,
        criteria=[],
        reasoning=reasoning,
        suggested_fixes=fixes,
    )


@pytest.fixture(scope="module")
def campaign():
    """A completed campaign with one REJECTED image attempt.

    The rejection is the point: it is the evidence the Learning lobe has to
    reason over, and a campaign where nothing failed teaches nothing.
    """
    image = Asset(
        id="a-img",
        campaign_id="live-brain",
        type="image",
        attempts=[
            Attempt(
                id="att-img-1",
                attempt_number=1,
                provider_name="p",
                model_name="m",
                prompt_used="pr",
                timestamp="2026-08-02T00:00:00Z",
                critique_verdict="FAIL",
                critique=_crit(
                    61,
                    False,
                    "The amber accent covers roughly half the frame and reads as "
                    "garish; the cup is dead-centre and shot like stock photography.",
                    "Reduce the accent to a small highlight; move the hero subject "
                    "off-centre under warm directional window light.",
                ),
                content=AttemptContent(
                    primary_color="#1E3A2B",
                    secondary_color="#F4F1EA",
                    accent_color="#D97706",
                ),
            ),
            Attempt(
                id="att-img-2",
                attempt_number=2,
                provider_name="p",
                model_name="m",
                prompt_used="pr2",
                timestamp="2026-08-02T00:01:00Z",
                critique_verdict="PASS",
                critique=_crit(
                    89,
                    True,
                    "Warm low window light across linen, cup off-centre, deep "
                    "forest green dominant with a restrained amber highlight.",
                    "None.",
                ),
                content=AttemptContent(
                    primary_color="#1E3A2B",
                    secondary_color="#F4F1EA",
                    accent_color="#D97706",
                ),
            ),
        ],
        final_approved_attempt_id="att-img-2",
        status="passed",
    )
    copy = Asset(
        id="a-copy",
        campaign_id="live-brain",
        type="copy",
        attempts=[
            Attempt(
                id="att-copy-1",
                attempt_number=1,
                provider_name="p",
                model_name="m",
                prompt_used="pr",
                timestamp="2026-08-02T00:02:00Z",
                critique_verdict="PASS",
                critique=_crit(87, True, "On tone.", "None."),
                content=AttemptContent(
                    headline="The hour that isn't spoken for",
                    subheadline="Single-origin coffee, delivered before you need it",
                    body_text="Some mornings are a sprint. This isn't for those.",
                    call_to_action="Start your first bag",
                    key_benefit_bullets=["Roasted to order", "Arrives early", "No contracts"],
                    social_posts=["The 20 minutes before the day starts.", "Coffee that waits."],
                ),
            )
        ],
        final_approved_attempt_id="att-copy-1",
        status="passed",
    )
    return Campaign(
        id="live-brain",
        brand_name=BRAND,
        product_service="single-origin coffee subscription",
        target_audience="urban professionals aged 28-45 who resent hustle culture",
        brief_text="warm, unhurried, anti-hustle",
        tone_tags=["Cozy & Warm"],
        colors=ColorPreference(primary="#1E3A2B", secondary="#F4F1EA", accent="#D97706"),
        created_at="2026-08-02T00:00:00Z",
        updated_at="2026-08-02T00:04:00Z",
        status="completed",
        assets=CampaignAssets(image=image, copy=copy),
        overall_quality_score=87,
        total_attempts_count=3,
        retry_count=1,
    )


# ------------------------------------------------------------------ routing
@needs_tokenrouter
def test_text_model_resolves_to_a_benchmarked_candidate(resolved):
    """Asserts the resolved model is one we measured, not a vendor name.

    The text model is deliberately swappable — what must hold is that whatever
    resolved came off the benchmarked list, so it is known to honour strict
    json_schema. Pinning the assertion to a brand would fail the moment the
    catalog shifts, which is exactly when this check should still be useful.
    """
    from app.providers.client import TEXT_CANDIDATES

    assert resolved.text_model in TEXT_CANDIDATES, (
        f"{resolved.text_model} was never benchmarked for strict-JSON compliance"
    )


@needs_tokenrouter
def test_a_free_tier_text_model_would_be_paced(resolved):
    """Free tiers carry hard request caps; the pacing must engage if one is pinned."""
    from app.providers.ratelimit import is_free_tier

    if resolved.text_model.endswith("-free"):
        assert is_free_tier(resolved.text_model), (
            "the resolved text model carries a free-tier cap but would not be paced"
        )
    else:
        # Paid models must NOT be throttled — pacing them would add minutes per
        # campaign for no reason.
        assert not is_free_tier(resolved.text_model)


# -------------------------------------------------------------------- lobes
@needs_tokenrouter
def test_strategy_lobe_produces_a_usable_directive(resolved, brief):
    strategy, manifest = lobes.strategize(brief, [], "live-brain-strategy")

    assert strategy is not None, "strategy lobe failed against the live model"
    assert strategy.big_idea.strip()
    assert strategy.visual_direction.strip()
    assert len(strategy.avoid) >= 2
    # Provenance: the brain's own reasoning is manifested like any asset.
    assert manifest


@needs_tokenrouter
def test_foresight_commits_to_a_scoreable_prediction(resolved, brief, campaign):
    foresight, _ = lobes.foresee(
        brief, [], None, load_brain(BRAND), "live-brain-foresight"
    )

    assert foresight is not None, "foresight lobe failed against the live model"
    assert 0 <= foresight.predicted_score <= 100
    # A truncated response yields an empty failure mode — the exact silent
    # failure that a too-low max_tokens produced during development.
    assert len(foresight.likely_failure_mode) > 20, "prediction looks truncated"

    scored = lobes.score_foresight(foresight, campaign)
    assert scored.calibration_error == abs(
        foresight.predicted_score - campaign.overall_quality_score
    )


@needs_tokenrouter
def test_audience_panel_is_diverse_and_reacts_in_character(resolved, brief, campaign):
    brain = load_brain(BRAND)
    brain.personas = []
    personas, _ = lobes.build_personas(brief, brain, "live-brain-personas")

    assert len(personas) == 4, f"expected a 4-person panel, got {len(personas)}"
    # A panel that agrees measures nothing — the prompt demands real spread.
    skepticisms = [p.skepticism for p in personas]
    assert max(skepticisms) - min(skepticisms) >= 20, f"panel too uniform: {skepticisms}"

    report, _ = lobes.simulate_audience(brief, personas, campaign, "live-brain-react")
    assert report is not None, "audience lobe failed against the live model"
    assert len(report.reactions) >= 3
    assert 0 <= report.resonance_score <= 100
    for reaction in report.reactions:
        assert reaction.quote.strip(), "a reaction with no quote is not a reaction"
        assert reaction.persona_id in {p.id for p in personas}
    assert report.basis, "the panel must state what it actually read"


@needs_tokenrouter
def test_learning_lobe_writes_laws_that_cite_this_run(resolved, brief, campaign):
    brain = load_brain(BRAND)
    delta, _ = lobes.learn(brief, campaign, brain, None, "live-brain-learn")

    assert delta is not None, "learning lobe failed against the live model"
    # Zero new laws is a legitimate answer, but any law returned must be sourced
    # — unsourced ones are dropped before they reach this object.
    for law in delta.laws_added:
        assert law.text.strip()
        assert law.evidence.strip()
        assert law.learned_from_campaign_id == "live-brain-learn"


# ------------------------------------------------------------- persistence
@needs_tokenrouter
def test_brain_persists_to_storage_and_measures_improvement(resolved, brief, campaign):
    """Two recorded runs must yield a real, computed improvement delta."""
    from app.brain.store import delete_brain

    slug = brand_slug(BRAND)
    delete_brain(slug)

    brain = load_brain(BRAND)
    assert brain.version == 0 and not brain.history

    # Run 1 — cold, no laws.
    brain.history.append(
        build_run_record(
            campaign,
            brain=brain,
            version_at_run=0,
            laws_available=0,
            resonance_score=61,
            predicted_score=80,
            calibration_error=7,
            forced_first_retry=False,
        )
    )
    brain.version = 1
    brain.lifetime_campaigns = 1
    save_brain(brain)

    assert compute_improvement(load_brain(BRAND)).has_baseline is False

    # Run 2 — warm, with laws.
    brain = load_brain(BRAND)
    better = campaign.model_copy(deep=True)
    better.id = "live-brain-2"
    better.retry_count = 0
    better.overall_quality_score = 93
    better.assets.image.attempts[0].critique.overall_score = 90
    better.assets.image.attempts[0].critique_verdict = "PASS"

    brain.history.append(
        build_run_record(
            better,
            brain=brain,
            version_at_run=1,
            laws_available=3,
            resonance_score=74,
            predicted_score=91,
            calibration_error=2,
            forced_first_retry=False,
        )
    )
    brain.version = 2
    brain.lifetime_campaigns = 2
    save_brain(brain)

    improvement = compute_improvement(load_brain(BRAND))
    assert improvement.has_baseline is True
    assert improvement.runs == 2
    assert improvement.first_attempt_score_delta > 0
    assert improvement.retry_delta < 0  # fewer retries is better
    assert improvement.resonance_delta == 13
    assert improvement.summary

    delete_brain(slug)
