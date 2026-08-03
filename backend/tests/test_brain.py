"""Campaign Brain — offline tests. No keys, no network.

Every lobe's inference call is stubbed at app.brain.lobes.brain_call, which is
the single seam all five share. That keeps these tests about the logic that
actually decides things — what gets saved, what gets discarded, how the
improvement number is computed — rather than about prompt strings.

The load-bearing assertions here are the ones that stop the demo from lying:
laws without evidence never reach storage, the improvement panel refuses to
claim a trend from one run, and a brain outage cannot change a campaign.
"""

from __future__ import annotations

import pytest

from app.brain import lobes
from app.brain.metrics import build_run_record, compute_improvement, first_attempt_scores
from app.brain.models import (
    AudienceReport,
    BrainState,
    BrandLaw,
    LearningDelta,
    Persona,
    PersonaReaction,
    RunRecord,
)
from app.brain.store import brand_slug, load_brain, save_brain, top_laws
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


# --------------------------------------------------------------- fixtures
def make_brief(brand: str = "Fernwood Coffee") -> CampaignBrief:
    return CampaignBrief(
        brand_name=brand,
        product_service="single-origin coffee subscription",
        target_audience="urban professionals aged 28-45",
        brief_text="warm, unhurried, anti-hustle",
        tone_tags=["Cozy & Warm"],
        colors=ColorPreference(primary="#1E3A2B", secondary="#F4F1EA", accent="#D97706"),
    )


def critique(score: int, passed: bool, pre_cap: int | None = None) -> CritiqueResult:
    return CritiqueResult(
        passed=passed,
        overall_score=score,
        criteria=[],
        reasoning=f"scored {score}",
        suggested_fixes="tighten the palette",
        pre_cap_score=pre_cap,
    )


def attempt(asset_type: str, n: int, score: int, passed: bool, pre_cap=None) -> Attempt:
    return Attempt(
        id=f"att-{asset_type}-{n}",
        attempt_number=n,
        provider_name="test",
        model_name="test-model",
        prompt_used="prompt",
        timestamp="2026-01-01T00:00:00Z",
        critique_verdict="PASS" if passed else "FAIL",
        critique=critique(score, passed, pre_cap),
        content=AttemptContent(headline="hi"),
    )


def make_campaign(
    *,
    campaign_id: str = "camp-1",
    image_attempts=((1, 70, False), (2, 90, True)),
    quality: int = 88,
    retries: int = 1,
) -> Campaign:
    image = Asset(
        id="asset-image",
        campaign_id=campaign_id,
        type="image",
        attempts=[attempt("image", n, s, p) for n, s, p in image_attempts],
        final_approved_attempt_id=f"att-image-{image_attempts[-1][0]}",
        status="passed",
    )
    copy = Asset(
        id="asset-copy",
        campaign_id=campaign_id,
        type="copy",
        attempts=[attempt("copy", 1, 86, True)],
        final_approved_attempt_id="att-copy-1",
        status="passed",
    )
    return Campaign(
        id=campaign_id,
        brand_name="Fernwood Coffee",
        product_service="coffee",
        target_audience="urban professionals",
        colors=ColorPreference(primary="#1E3A2B", secondary="#F4F1EA", accent="#D97706"),
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        status="completed",
        assets=CampaignAssets(image=image, copy=copy),
        overall_quality_score=quality,
        total_attempts_count=len(image.attempts) + 1,
        retry_count=retries,
    )


# ------------------------------------------------------------------ store
def test_brand_slug_is_stable_across_punctuation_and_case():
    """Three spellings of one brand must not become three empty brains."""
    assert brand_slug("Fernwood Coffee") == "fernwood-coffee"
    assert brand_slug("fernwood  coffee!") == "fernwood-coffee"
    assert brand_slug("  FERNWOOD-COFFEE ") == "fernwood-coffee"
    assert brand_slug("") == "unnamed-brand"


def test_load_brain_returns_empty_brain_for_unknown_brand():
    brain = load_brain("Nobody's Brand")
    assert brain.version == 0
    assert brain.laws == []
    assert brain.history == []


def test_save_then_load_round_trips_laws_and_history():
    brain = load_brain("Fernwood Coffee")
    brain.version = 3
    brain.laws.append(
        BrandLaw(
            id="law-1",
            text="Warmth must come from lighting, not orange saturation.",
            category="visual",
            source="critique",
            confidence=80,
            evidence="attempt #1 scored 58: 'the orange reads as garish'",
            learned_from_campaign_id="camp-1",
            learned_at="2026-01-01T00:00:00Z",
        )
    )
    save_brain(brain)

    reloaded = load_brain("Fernwood Coffee")
    assert reloaded.version == 3
    assert len(reloaded.laws) == 1
    assert reloaded.laws[0].evidence.startswith("attempt #1")


def test_top_laws_ranks_reinforcement_above_raw_confidence():
    """A lesson two campaigns found independently outranks one strong guess."""
    brain = BrainState(brand_slug="x", brand_name="X")
    brain.laws = [
        BrandLaw(
            id="confident-but-unconfirmed",
            text="a",
            category="copy",
            source="critique",
            confidence=99,
            evidence="e",
            learned_from_campaign_id="c",
            learned_at="t",
            reinforced_count=1,
        ),
        BrandLaw(
            id="twice-confirmed",
            text="b",
            category="copy",
            source="critique",
            confidence=60,
            evidence="e",
            learned_from_campaign_id="c",
            learned_at="t",
            reinforced_count=3,
        ),
    ]
    assert top_laws(brain)[0].id == "twice-confirmed"


# ---------------------------------------------------------------- metrics
def test_first_attempt_scores_prefer_the_pre_cap_value():
    """FERNWOOD_FORCE_FIRST_RETRY must not depress the learning signal.

    The demo harness caps the first image critique at 82 to guarantee a visible
    retry. Scoring the brain against a number the harness chose would measure
    the harness, not the brain.
    """
    campaign = make_campaign(image_attempts=((1, 70, False), (2, 90, True)))
    campaign.assets.image.attempts[0].critique.pre_cap_score = 93

    scores = first_attempt_scores(campaign)
    assert 93 in scores
    assert 70 not in scores


def test_improvement_refuses_to_claim_a_trend_from_one_run():
    brain = BrainState(brand_slug="x", brand_name="Fernwood Coffee")
    brain.history = [
        RunRecord(
            campaign_id="camp-1",
            brand_name="Fernwood Coffee",
            created_at="t",
            brain_version_at_run=0,
            laws_available=0,
            total_attempts=3,
            retry_count=2,
            first_attempt_avg_score=70,
            final_quality_score=88,
        )
    ]
    delta = compute_improvement(brain)
    assert delta.has_baseline is False
    assert delta.runs == 1
    assert "baseline" in delta.summary.lower()


def test_improvement_reports_gains_between_first_and_latest_run():
    brain = BrainState(brand_slug="x", brand_name="Fernwood Coffee")
    brain.history = [
        RunRecord(
            campaign_id="camp-1",
            brand_name="Fernwood Coffee",
            created_at="t1",
            brain_version_at_run=0,
            laws_available=0,
            total_attempts=5,
            retry_count=4,
            first_attempt_avg_score=68,
            final_quality_score=86,
            resonance_score=61,
        ),
        RunRecord(
            campaign_id="camp-2",
            brand_name="Fernwood Coffee",
            created_at="t2",
            brain_version_at_run=2,
            laws_available=7,
            total_attempts=3,
            retry_count=1,
            first_attempt_avg_score=86,
            final_quality_score=92,
            resonance_score=74,
        ),
    ]
    delta = compute_improvement(brain)
    assert delta.has_baseline is True
    assert delta.first_attempt_score_delta == 18
    assert delta.retry_delta == -3  # negative is better
    assert delta.quality_delta == 6
    assert delta.resonance_delta == 13
    assert delta.laws_delta == 7
    assert "sooner" in delta.summary


def test_improvement_discloses_mismatched_run_conditions():
    """A comparison made under different settings must say so, not overstate."""
    brain = BrainState(brand_slug="x", brand_name="X")
    brain.history = [
        RunRecord(
            campaign_id="camp-1",
            brand_name="X",
            created_at="t1",
            brain_version_at_run=0,
            laws_available=0,
            total_attempts=4,
            retry_count=3,
            first_attempt_avg_score=70,
            final_quality_score=85,
            forced_first_retry=True,
        ),
        RunRecord(
            campaign_id="camp-2",
            brand_name="X",
            created_at="t2",
            brain_version_at_run=1,
            laws_available=3,
            total_attempts=3,
            retry_count=1,
            first_attempt_avg_score=90,
            final_quality_score=91,
            forced_first_retry=False,
        ),
    ]
    delta = compute_improvement(brain)
    assert delta.caveat
    assert "not like-for-like" in delta.caveat


def test_run_record_credits_the_version_the_run_actually_used():
    """Learning bumps the live brain before this is called.

    Reading brain.version here would credit the run with laws it never saw, and
    every improvement comparison is built on these records.
    """
    brain = BrainState(brand_slug="x", brand_name="Fernwood Coffee", version=3)
    record = build_run_record(
        make_campaign(),
        brain=brain,
        version_at_run=2,
        laws_available=4,
        resonance_score=None,
        predicted_score=None,
        calibration_error=None,
        forced_first_retry=False,
    )
    assert record.brain_version_at_run == 2


def test_build_run_record_captures_the_campaign_outcome():
    brain = BrainState(brand_slug="x", brand_name="Fernwood Coffee", version=2)
    record = build_run_record(
        make_campaign(quality=91, retries=1),
        brain=brain,
        version_at_run=2,
        laws_available=4,
        resonance_score=72,
        predicted_score=88,
        calibration_error=3,
        forced_first_retry=False,
    )
    assert record.brain_version_at_run == 2
    assert record.laws_available == 4
    assert record.final_quality_score == 91
    assert record.resonance_score == 72
    assert record.calibration_error == 3


# ------------------------------------------------------------------ lobes
def test_learn_discards_laws_that_cite_no_evidence(monkeypatch):
    """A law without a citation is an opinion, and opinions do not get saved."""
    monkeypatch.setattr(
        lobes,
        "brain_call",
        lambda *a, **k: (
            {
                "summary": "s",
                "reinforcedLawIds": [],
                "newLaws": [
                    {
                        "text": "Grounded rule",
                        "category": "visual",
                        "confidence": 80,
                        "evidence": "attempt #1 scored 58: palette too hot",
                    },
                    {
                        "text": "Unsourced vibe",
                        "category": "visual",
                        "confidence": 95,
                        "evidence": "",
                    },
                ],
            },
            "hash-1",
        ),
    )

    brain = BrainState(brand_slug="x", brand_name="X")
    delta, _ = lobes.learn(make_brief(), make_campaign(), brain, None, "camp-1")

    assert delta is not None
    assert [law.text for law in delta.laws_added] == ["Grounded rule"]


def test_learn_ignores_reinforcement_of_laws_that_do_not_exist(monkeypatch):
    """Reinforcement raises a law's influence, so a hallucinated id must not count."""
    monkeypatch.setattr(
        lobes,
        "brain_call",
        lambda *a, **k: (
            {"summary": "s", "reinforcedLawIds": ["law-real", "law-invented"], "newLaws": []},
            None,
        ),
    )
    brain = BrainState(brand_slug="x", brand_name="X")
    brain.laws = [
        BrandLaw(
            id="law-real",
            text="t",
            category="copy",
            source="critique",
            confidence=50,
            evidence="e",
            learned_from_campaign_id="c",
            learned_at="t",
        )
    ]

    delta, _ = lobes.learn(make_brief(), make_campaign(), brain, None, "camp-2")
    assert delta.laws_reinforced == ["law-real"]


def test_learn_drops_a_law_that_duplicates_an_existing_one(monkeypatch):
    monkeypatch.setattr(
        lobes,
        "brain_call",
        lambda *a, **k: (
            {
                "summary": "s",
                "reinforcedLawIds": [],
                "newLaws": [
                    {
                        "text": "Warmth from lighting, not saturation",
                        "category": "visual",
                        "confidence": 70,
                        "evidence": "critique said so again",
                    }
                ],
            },
            None,
        ),
    )
    brain = BrainState(brand_slug="x", brand_name="X")
    brain.laws = [
        BrandLaw(
            id="law-existing",
            text="Warmth from lighting, not saturation",
            category="visual",
            source="critique",
            confidence=70,
            evidence="e",
            learned_from_campaign_id="c",
            learned_at="t",
        )
    ]
    delta, _ = lobes.learn(make_brief(), make_campaign(), brain, None, "camp-3")
    assert delta.laws_added == []


def test_apply_learning_bumps_version_and_reinforcement():
    brain = BrainState(brand_slug="x", brand_name="X", version=1)
    brain.laws = [
        BrandLaw(
            id="law-1",
            text="t",
            category="copy",
            source="critique",
            confidence=60,
            evidence="e",
            learned_from_campaign_id="c",
            learned_at="t",
            reinforced_count=1,
        )
    ]
    delta = LearningDelta(
        laws_added=[
            BrandLaw(
                id="law-2",
                text="new",
                category="voice",
                source="audience",
                confidence=70,
                evidence="e",
                learned_from_campaign_id="c2",
                learned_at="t",
            )
        ],
        laws_reinforced=["law-1"],
        version_before=1,
        version_after=2,
    )

    lobes.apply_learning(brain, delta)
    assert brain.version == 2
    assert len(brain.laws) == 2
    assert brain.laws[0].reinforced_count == 2
    assert brain.laws[0].confidence == 65


def test_reinforcement_confidence_is_capped_below_certainty():
    """Repeated agreement is evidence, not proof — nothing reaches 100."""
    brain = BrainState(brand_slug="x", brand_name="X")
    brain.laws = [
        BrandLaw(
            id="law-1",
            text="t",
            category="copy",
            source="critique",
            confidence=98,
            evidence="e",
            learned_from_campaign_id="c",
            learned_at="t",
        )
    ]
    lobes.apply_learning(
        brain, LearningDelta(laws_reinforced=["law-1"], version_before=0, version_after=1)
    )
    assert brain.laws[0].confidence == 99


def test_resonance_weights_intent_below_sentiment():
    """Admiring an ad without acting on it is a real outcome and must show."""
    admired = [
        PersonaReaction(
            persona_id=f"p{i}",
            persona_name=f"P{i}",
            sentiment=90,
            verdict="loves",
            quote="q",
            objection="",
            would_act=10,
            attention_seconds=2.0,
        )
        for i in range(4)
    ]
    # 0.6*90 + 0.4*10 = 58 — well below the 90 a sentiment-only score would give.
    assert lobes._resonance(admired) == 58


def test_polarization_separates_a_split_panel_from_a_lukewarm_one():
    def panel(scores):
        return [
            PersonaReaction(
                persona_id=f"p{i}",
                persona_name=f"P{i}",
                sentiment=s,
                verdict="likes",
                quote="q",
                objection="",
                would_act=s,
                attention_seconds=1.0,
            )
            for i, s in enumerate(scores)
        ]

    split = panel([95, 95, 5, 5])
    lukewarm = panel([50, 50, 50, 50])

    assert lobes._resonance(split) == lobes._resonance(lukewarm) == 50
    assert lobes._polarization(split) == 45
    assert lobes._polarization(lukewarm) == 0


def test_audience_reaction_matches_personas_by_name(monkeypatch):
    personas = [
        Persona(
            id="persona-x-1",
            name="Maya Rodriguez",
            age=34,
            occupation="nurse",
            location="Portland",
            mindset="tired",
            skepticism=70,
            media_diet="instagram",
        )
    ]
    monkeypatch.setattr(
        lobes,
        "brain_call",
        lambda *a, **k: (
            {
                "consensus": "mixed",
                "topObjection": "unclear product",
                "reactions": [
                    {
                        "personaName": "Maya Rodriguez",
                        "sentiment": 40,
                        "verdict": "indifferent",
                        "quote": "I could not tell you what they sell.",
                        "objection": "no product clarity",
                        "wouldAct": 15,
                        "attentionSeconds": 1.2,
                    }
                ],
            },
            "h",
        ),
    )
    report, _ = lobes.simulate_audience(make_brief(), personas, make_campaign(), "camp-1")
    assert report is not None
    assert report.reactions[0].persona_id == "persona-x-1"
    assert report.reactions[0].sentiment == 40
    assert report.basis  # the panel must state what it actually read


def test_audience_reaction_falls_back_positionally_on_a_paraphrased_name(monkeypatch):
    """Models paraphrase names back; that must not silently shrink the panel."""
    personas = [
        Persona(
            id="persona-x-1",
            name="Maya Rodriguez",
            age=34,
            occupation="nurse",
            location="Portland",
            mindset="tired",
            skepticism=70,
            media_diet="instagram",
        )
    ]
    monkeypatch.setattr(
        lobes,
        "brain_call",
        lambda *a, **k: (
            {
                "consensus": "c",
                "topObjection": "o",
                "reactions": [
                    {
                        "personaName": "Maya R.",
                        "sentiment": 55,
                        "verdict": "likes",
                        "quote": "q",
                        "objection": "o",
                        "wouldAct": 30,
                        "attentionSeconds": 2.0,
                    }
                ],
            },
            None,
        ),
    )
    report, _ = lobes.simulate_audience(make_brief(), personas, make_campaign(), "camp-1")
    assert report is not None
    assert len(report.reactions) == 1
    assert report.reactions[0].persona_id == "persona-x-1"


def test_personas_are_reused_rather_than_regenerated(monkeypatch):
    """A resonance trend is meaningless if the judges change between runs."""
    called = []
    monkeypatch.setattr(
        lobes, "brain_call", lambda *a, **k: (called.append(1), ({}, None))[1]
    )
    brain = BrainState(brand_slug="x", brand_name="X")
    brain.personas = [
        Persona(
            id="persona-x-1",
            name="Maya",
            age=30,
            occupation="nurse",
            location="PDX",
            mindset="m",
            skepticism=50,
            media_diet="d",
        )
    ]
    personas, manifest = lobes.build_personas(make_brief(), brain, "camp-2")
    assert personas == brain.personas
    assert called == []  # no inference call was made


def test_score_foresight_records_error_even_when_unflattering():
    from app.brain.models import Foresight

    foresight = Foresight(
        predicted_score=95,
        predicted_retries=0,
        likely_failure_mode="none",
        confidence=90,
    )
    campaign = make_campaign(quality=61, retries=4)
    scored = lobes.score_foresight(foresight, campaign)

    assert scored.actual_score == 61
    assert scored.calibration_error == 34
    assert scored.actual_retries == 4


# -------------------------------------------------------- degradation path
def test_every_lobe_degrades_to_none_when_inference_fails(monkeypatch):
    """A brain outage must never become a campaign failure."""
    monkeypatch.setattr(lobes, "brain_call", lambda *a, **k: (None, None))
    brief = make_brief()
    brain = BrainState(brand_slug="x", brand_name="X")

    assert lobes.strategize(brief, [], "camp-1") == (None, None)
    assert lobes.foresee(brief, [], None, brain, "camp-1") == (None, None)
    assert lobes.build_personas(brief, brain, "camp-1") == ([], None)
    assert lobes.learn(brief, make_campaign(), brain, None, "camp-1") == (None, None)


def test_strategy_without_a_big_idea_is_rejected(monkeypatch):
    """An empty directive injected into every prompt is worse than none."""
    monkeypatch.setattr(
        lobes,
        "brain_call",
        lambda *a, **k: (
            {
                "bigIdea": "   ",
                "positioning": "p",
                "visualDirection": "v",
                "voiceDirection": "vo",
                "copyAngle": "c",
                "avoid": ["x"],
            },
            "h",
        ),
    )
    strategy, _ = lobes.strategize(make_brief(), [], "camp-1")
    assert strategy is None


def test_simulate_audience_returns_none_without_a_panel():
    report, manifest = lobes.simulate_audience(make_brief(), [], make_campaign(), "camp-1")
    assert report is None and manifest is None


# ----------------------------------------------------------------- prompts
def test_rejection_block_carries_every_failed_attempt_with_its_critique():
    from app.brain.prompts import rejection_block

    block = rejection_block(make_campaign(image_attempts=((1, 58, False), (2, 90, True))))
    assert "attempt #1" in block
    assert "58/100" in block
    assert "tighten the palette" in block


def test_rejection_block_states_plainly_when_nothing_failed():
    from app.brain.prompts import rejection_block

    block = rejection_block(make_campaign(image_attempts=((1, 92, True),)))
    assert "Nothing was rejected" in block


def test_strategy_block_injects_learned_anti_patterns_into_prompts():
    """A law only matters if it reaches the next campaign's prompt."""
    from app.brain.models import CampaignStrategy
    from app.domain.prompts import build_copy_prompt

    strategy = CampaignStrategy(
        big_idea="Coffee for the unhurried hour",
        positioning="p",
        visual_direction="v",
        voice_direction="vo",
        copy_angle="Lead with time, not beans",
        avoid=["never say 'artisanal'", "no hustle-culture framing"],
    )
    prompt = build_copy_prompt(make_brief(), 1, None, strategy)

    assert "Coffee for the unhurried hour" in prompt
    assert "never say 'artisanal'" in prompt
    assert "Lead with time, not beans" in prompt


def test_image_prompt_sanitizes_hex_codes_out_of_strategy_text():
    """Image models letter hex codes into the frame; strategy text is free-form."""
    from app.brain.models import CampaignStrategy
    from app.domain.prompts import build_image_prompt

    strategy = CampaignStrategy(
        big_idea="Warmth",
        positioning="p",
        visual_direction="lean on #1E3A2B against a palette strip",
        voice_direction="vo",
        copy_angle="c",
        avoid=["no #D97706 dominance"],
    )
    prompt = build_image_prompt(make_brief(), 1, None, strategy)

    assert "#1E3A2B" not in prompt
    assert "#D97706" not in prompt

    # Only the injected strategy is under test. The base prompt legitimately
    # contains "palette strips" in its own negative instruction to the model.
    strategy_section = prompt.split("CAMPAIGN STRATEGY")[1]
    assert "palette strip" not in strategy_section
    assert "colour treatment" in strategy_section
    # The block must start on its own line rather than running into the
    # preceding sentence — sanitizing strips leading whitespace.
    assert "\n\nCAMPAIGN STRATEGY" in prompt


def test_prompts_are_unchanged_when_the_brain_is_absent():
    """Strategy is optional — a skipped brain must not alter generation."""
    from app.domain.prompts import build_copy_prompt, build_image_prompt

    brief = make_brief()
    assert build_copy_prompt(brief, 1, None, None) == build_copy_prompt(brief, 1, None)
    assert build_image_prompt(brief, 1, None, None) == build_image_prompt(brief, 1, None)


# --------------------------------------------------------------------- api
def test_brain_api_round_trip():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        # Unknown brand: 200 with an empty brain, because a cold start is the
        # normal first case rather than an error.
        res = client.get("/api/brain/by-brand/Fernwood%20Coffee")
        assert res.status_code == 200
        assert res.json()["brain"]["version"] == 0
        assert res.json()["improvement"]["hasBaseline"] is False

        brain = load_brain("Fernwood Coffee")
        brain.version = 1
        brain.laws.append(
            BrandLaw(
                id="law-1",
                text="t",
                category="visual",
                source="critique",
                confidence=70,
                evidence="e",
                learned_from_campaign_id="camp-1",
                learned_at="t",
            )
        )
        save_brain(brain)

        listed = client.get("/api/brains").json()
        assert listed["count"] == 1

        fetched = client.get("/api/brain/fernwood-coffee").json()
        assert len(fetched["brain"]["laws"]) == 1
        assert fetched["brain"]["laws"][0]["evidence"] == "e"

        assert client.delete("/api/brain/fernwood-coffee").status_code == 204
        assert client.get("/api/brain/fernwood-coffee").status_code == 404


def test_campaign_serializes_its_brain_snapshot_in_camel_case():
    """campaign.brain must reach the browser in the shape src/types.ts declares."""
    from app.brain.models import BrainSnapshot

    campaign = make_campaign()
    snapshot = BrainSnapshot(
        brand_slug="fernwood-coffee",
        brand_name="Fernwood Coffee",
        cold_start=False,
        brain_version_before=2,
        brain_version_after=3,
        lobes={"recall": "done"},
    )
    campaign.brain = snapshot.ts()

    payload = campaign.ts()
    assert payload["brain"]["brandSlug"] == "fernwood-coffee"
    assert payload["brain"]["brainVersionAfter"] == 3
    assert payload["brain"]["coldStart"] is False
