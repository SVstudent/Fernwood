"""Storyboard parsing and the ad track's degradation paths.

The storyboard is what makes the output an advertisement rather than a moving
photograph, so the assertions here are mostly about REFUSING bad shot lists:
one shot is not an ad, and a scene description carrying hex codes gets those
codes lettered into the frame by the image model.
"""

from __future__ import annotations

import pytest

from app.domain.models import CampaignBrief, ColorPreference
from app.pipeline import storyboard as sb


def brief(brand: str = "Fernwood Coffee") -> CampaignBrief:
    return CampaignBrief(
        brand_name=brand,
        product_service="single-origin coffee subscription",
        target_audience="urban professionals aged 28-45",
        brief_text="warm, unhurried",
        tone_tags=["Cozy & Warm"],
        colors=ColorPreference(primary="#1E3A2B", secondary="#F4F1EA", accent="#D97706"),
    )


def shot(role="hook", title="T", scene="A warm kitchen at dawn", motion="slow push-in", line=""):
    return {
        "role": role,
        "title": title,
        "scenePrompt": scene,
        "motionPrompt": motion,
        "voiceoverLine": line,
    }


def stub(monkeypatch, payload, manifest="hash-1"):
    monkeypatch.setattr(sb, "brain_call", lambda *a, **k: (payload, manifest))


# ------------------------------------------------------------------ parsing
def test_storyboard_produces_ordered_indexed_shots(monkeypatch):
    stub(
        monkeypatch,
        {
            "shots": [
                shot("hook", "Dawn", "An empty kitchen before anyone wakes", "slow push-in", "There's an hour"),
                shot("product", "The Bag", "A close tactile shot of a coffee bag", "parallax drift", "we roast for it"),
                shot("benefit", "First Sip", "Hands cradling a warm cup by a window", "slow tilt", "Fernwood."),
            ]
        },
    )
    shots, manifest = sb.build_storyboard(
        brief(),
        campaign_id="c1",
        strategy=None,
        voiceover_script="There's an hour we roast for it Fernwood.",
        approved_visual_description="warm window light",
        shot_count=3,
        seconds_per_shot=6,
    )

    assert [s.index for s in shots] == [0, 1, 2]
    assert [s.role for s in shots] == ["hook", "product", "benefit"]
    assert all(s.duration_seconds == 6 for s in shots)
    assert all(s.status == "pending" for s in shots)
    assert manifest == "hash-1"


def test_every_shot_is_a_distinct_scene(monkeypatch):
    """Four angles on one table is the thing this feature exists to stop."""
    stub(
        monkeypatch,
        {
            "shots": [
                shot("hook", "A", "An empty kitchen before anyone wakes"),
                shot("product", "B", "A close tactile shot of a coffee bag"),
                shot("benefit", "C", "Hands cradling a warm cup by a window"),
            ]
        },
    )
    shots, _ = sb.build_storyboard(
        brief(), campaign_id="c1", strategy=None, voiceover_script="s",
        approved_visual_description="d", shot_count=3, seconds_per_shot=6,
    )
    assert len({s.scene_prompt for s in shots}) == 3
    assert len({s.motion_prompt for s in shots}) >= 1


def test_scene_prompts_are_sanitized_of_hex_and_swatch_language(monkeypatch):
    """These strings go straight to an image model, which letters them in."""
    stub(
        monkeypatch,
        {
            "shots": [
                shot("hook", "A", "Kitchen lit in #1E3A2B with a palette strip on the wall"),
                shot("product", "B", "Bag against a #D97706 swatch backdrop"),
            ]
        },
    )
    shots, _ = sb.build_storyboard(
        brief(), campaign_id="c1", strategy=None, voiceover_script="s",
        approved_visual_description="d", shot_count=3, seconds_per_shot=6,
    )
    blob = " ".join(s.scene_prompt for s in shots)
    assert "#1E3A2B" not in blob
    assert "#D97706" not in blob
    assert "palette strip" not in blob
    assert "swatch" not in blob


def test_a_single_shot_is_rejected_as_not_an_advertisement(monkeypatch):
    stub(monkeypatch, {"shots": [shot("hook", "Only", "One lonely scene")]})
    shots, manifest = sb.build_storyboard(
        brief(), campaign_id="c1", strategy=None, voiceover_script="s",
        approved_visual_description="d", shot_count=3, seconds_per_shot=6,
    )
    assert shots == []
    assert manifest == "hash-1"  # the attempt is still recorded


def test_shots_without_a_scene_are_dropped(monkeypatch):
    stub(
        monkeypatch,
        {
            "shots": [
                shot("hook", "A", "A real scene"),
                shot("product", "B", "   "),
                shot("benefit", "C", "Another real scene"),
            ]
        },
    )
    shots, _ = sb.build_storyboard(
        brief(), campaign_id="c1", strategy=None, voiceover_script="s",
        approved_visual_description="d", shot_count=4, seconds_per_shot=6,
    )
    assert len(shots) == 2
    assert [s.index for s in shots] == [0, 1]  # reindexed, no gap


def test_an_unknown_role_falls_back_positionally(monkeypatch):
    """Ordering already carries the narrative; a bad label still cuts."""
    stub(
        monkeypatch,
        {
            "shots": [
                shot("establishing", "A", "Scene one"),
                shot("montage", "B", "Scene two"),
                shot("cta", "C", "Scene three"),
            ]
        },
    )
    shots, _ = sb.build_storyboard(
        brief(), campaign_id="c1", strategy=None, voiceover_script="s",
        approved_visual_description="d", shot_count=3, seconds_per_shot=6,
    )
    assert [s.role for s in shots] == ["hook", "product", "cta"]


def test_shot_count_is_capped(monkeypatch):
    stub(monkeypatch, {"shots": [shot("hook", f"S{i}", f"Scene {i}") for i in range(6)]})
    shots, _ = sb.build_storyboard(
        brief(), campaign_id="c1", strategy=None, voiceover_script="s",
        approved_visual_description="d", shot_count=3, seconds_per_shot=6,
    )
    assert len(shots) == 3


def test_storyboard_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(sb, "brain_call", lambda *a, **k: (None, None))
    assert sb.build_storyboard(
        brief(), campaign_id="c1", strategy=None, voiceover_script="s",
        approved_visual_description="d", shot_count=3, seconds_per_shot=6,
    ) == ([], None)


# ----------------------------------------------------------------- prompting
def test_prompt_carries_the_recorded_voiceover_verbatim():
    """The script is already generated, critiqued and transcription-verified."""
    script = "There's an hour before the day asks anything of you."
    prompt = sb.storyboard_prompt(brief(), None, script, "warm light", 3, 6)
    assert script in prompt
    assert "use its exact words" in prompt
    assert "do not rewrite" in prompt


def test_prompt_injects_the_campaign_strategy_and_its_antipatterns():
    from app.brain.models import CampaignStrategy

    strategy = CampaignStrategy(
        big_idea="A protected pause in the day",
        positioning="p",
        visual_direction="Warm window light, off-centre subject",
        voice_direction="v",
        copy_angle="c",
        avoid=["no hustle-coded imagery", "no laptops"],
    )
    prompt = sb.storyboard_prompt(brief(), strategy, "script", "desc", 3, 6)
    assert "A protected pause in the day" in prompt
    assert "no hustle-coded imagery" in prompt


def test_prompt_forbids_text_in_frame():
    """Generated lettering comes out malformed; the end card supplies the words."""
    prompt = sb.storyboard_prompt(brief(), None, "s", "d", 3, 6)
    assert "no text" in prompt.lower()
    assert "watermark" in prompt.lower()


def test_prompt_scales_its_stated_runtime_with_shot_count():
    assert "18-second" in sb.storyboard_prompt(brief(), None, "s", "d", 3, 6)
    assert "24-second" in sb.storyboard_prompt(brief(), None, "s", "d", 4, 6)


# ------------------------------------------------------------------ fallback
def test_fallback_is_still_multi_shot():
    """Losing the model should cost the writing, not the format."""
    shots = sb.fallback_storyboard(brief(), 3, 6)
    assert len(shots) == 3
    assert len({s.scene_prompt for s in shots}) == 3
    assert len({s.motion_prompt for s in shots}) == 3
    assert [s.role for s in shots] == ["hook", "product", "benefit"]


def test_fallback_scenes_carry_the_brief_palette_in_words():
    shots = sb.fallback_storyboard(brief(), 3, 6)
    blob = " ".join(s.scene_prompt for s in shots).lower()
    assert "forest green" in blob  # #1E3A2B rendered as words
    assert "#" not in blob


def test_fallback_respects_shot_count():
    assert len(sb.fallback_storyboard(brief(), 4, 6)) == 4
    assert len(sb.fallback_storyboard(brief(), 2, 6)) == 2


# ----------------------------------------------------------------- ad track
def test_ad_track_skips_cleanly_without_an_approved_visual():
    from app.pipeline.ad import run_ad_track
    from app.runtime.logbus import Emitter

    assert run_ad_track(brief(), "c1", Emitter("c1"), None, None, None, None) is None


def test_ad_track_skips_on_local_storage_with_an_actionable_message(monkeypatch):
    """Image-to-video needs an https first frame; local disk cannot provide one."""
    from app.pipeline import ad
    from app.runtime.logbus import Emitter

    messages = []
    monkeypatch.setattr(
        Emitter, "warning",
        lambda self, stage, title, msg, **kw: messages.append((title, msg)),
    )

    image = _fake_image_asset()
    assert ad.run_ad_track(brief(), "c1", Emitter("c1"), image, None, None, None) is None
    assert messages
    assert "b2" in messages[0][1].lower()


def _fake_image_asset():
    from app.domain.models import Asset, Attempt, AttemptContent, CritiqueResult

    return Asset(
        id="a", campaign_id="c1", type="image",
        attempts=[
            Attempt(
                id="att-1", attempt_number=1, provider_name="p", model_name="m",
                prompt_used="pr", timestamp="2026-08-02T00:00:00Z",
                critique_verdict="PASS",
                critique=CritiqueResult(
                    passed=True, overall_score=90, criteria=[],
                    reasoning="warm light", suggested_fixes="none",
                ),
                content=AttemptContent(
                    image_url="/api/media/x.jpg",
                    primary_color="#1E3A2B", accent_color="#D97706",
                ),
            )
        ],
        final_approved_attempt_id="att-1", status="passed",
    )


def test_ad_critique_states_plainly_that_motion_was_not_scored():
    """Overstating what was verified is worse than a modest claim."""
    from app.domain.models import AdShot
    from app.pipeline.ad import _critique

    shots = [
        AdShot(index=i, role=r, title="T", scene_prompt="s", motion_prompt="m", duration_seconds=6, status="rendered")
        for i, r in enumerate(["hook", "product", "benefit"])
    ]
    result = _critique(shots, has_vo=True, has_card=True, approved_image=None)

    assert "not independently scored" in result.suggested_fixes
    assert any(c.name == "Narrative Structure" and c.passed for c in result.criteria)
    assert any(c.name == "Delivery Completeness" and c.score == 100 for c in result.criteria)


def test_ad_critique_marks_incomplete_delivery_when_pieces_are_missing():
    from app.domain.models import AdShot
    from app.pipeline.ad import _critique

    shots = [AdShot(index=0, role="hook", title="T", scene_prompt="s", motion_prompt="m", duration_seconds=6, status="rendered")]
    result = _critique(shots, has_vo=False, has_card=False, approved_image=None)

    completeness = next(c for c in result.criteria if c.name == "Delivery Completeness")
    assert completeness.passed is False
    assert "absent" in completeness.feedback
    structure = next(c for c in result.criteria if c.name == "Narrative Structure")
    assert structure.passed is False  # one shot is not an ad


def test_ad_shots_serialize_to_the_typescript_contract():
    from app.domain.models import AdShot, AttemptContent

    content = AttemptContent(
        video_url="/api/media/ad.mp4",
        ad_shots=[
            AdShot(index=0, role="hook", title="Dawn", scene_prompt="s",
                   motion_prompt="m", duration_seconds=6, status="rendered")
        ],
        shot_count=1,
        has_voiceover=True,
        has_end_card=True,
    )
    payload = content.ts()
    assert payload["adShots"][0]["scenePrompt"] == "s"
    assert payload["adShots"][0]["durationSeconds"] == 6
    assert payload["shotCount"] == 1
    assert payload["hasVoiceover"] is True
