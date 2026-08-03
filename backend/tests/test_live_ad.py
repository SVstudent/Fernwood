"""Live advertisement production — generates a REAL multi-shot ad and inspects it.

    uv run pytest tests/test_live_ad.py -m live -v -s

Expensive: one image generation and one video generation per shot, ~3-5 minutes.
Skipped by default.

This is the test that proves the feature is what it claims. The claim is "a cut
advertisement, not one still in motion", and the only way to check it is to
produce the file and interrogate it:

  * more than one shot actually rendered
  * the shots are DIFFERENT scenes (distinct frames, distinct prompts)
  * the finished mp4 is longer than any single clip — i.e. concatenation
    genuinely happened rather than one shot being delivered
  * it carries an audio stream, because an ad without its voiceover is a gif
  * every shot and the final cut carry provenance
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.domain.models import (
    Asset,
    Attempt,
    AttemptContent,
    CampaignBrief,
    ColorPreference,
    CritiqueResult,
)
from app.pipeline import assemble
from app.providers.client import probe_models
from app.runtime.logbus import Emitter

pytestmark = pytest.mark.live

_settings = get_settings()

needs_b2 = pytest.mark.skipif(
    _settings.fernwood_storage.lower() != "b2" or not _settings.has_b2,
    reason="the advertisement track needs B2 so shot frames can be presigned",
)
needs_tokenrouter = pytest.mark.skipif(
    not _settings.has_tokenrouter, reason="TOKENROUTER_API_KEY not set"
)
needs_ffmpeg = pytest.mark.skipif(
    assemble.ffmpeg_exe() is None, reason="ffmpeg unavailable"
)


BRIEF = CampaignBrief(
    brand_name="Fernwood Live Ad",
    product_service="single-origin coffee subscription",
    target_audience="urban professionals aged 28-45 who resent hustle culture",
    brief_text="warm, unhurried, anti-hustle",
    tone_tags=["Cozy & Warm"],
    colors=ColorPreference(primary="#1E3A2B", secondary="#F4F1EA", accent="#D97706"),
    include_video=True,
)


def _crit(score: int) -> CritiqueResult:
    return CritiqueResult(
        passed=True,
        overall_score=score,
        criteria=[],
        reasoning=(
            "Warm low window light across a linen surface, cup off-centre, deep "
            "forest green dominant with a restrained amber highlight."
        ),
        suggested_fixes="None.",
    )


def _asset(kind: str, content: AttemptContent) -> Asset:
    return Asset(
        id=f"a-{kind}",
        campaign_id="live-ad",
        type=kind,  # type: ignore[arg-type]
        attempts=[
            Attempt(
                id=f"att-{kind}-1",
                attempt_number=1,
                provider_name="p",
                model_name="m",
                prompt_used="pr",
                timestamp="2026-08-02T00:00:00Z",
                critique_verdict="PASS",
                critique=_crit(89),
                content=content,
            )
        ],
        final_approved_attempt_id=f"att-{kind}-1",
        status="passed",
    )


class Produced:
    """The finished ad plus its bytes, captured together.

    The bytes are downloaded inside the module-scoped fixture rather than in the
    test that inspects them, because conftest's autouse `isolated_storage`
    fixture redirects the storage backend to a per-test tmp_path. That fixture
    is function-scoped, so it re-points the backend at empty local disk AFTER
    this module-scoped fixture has produced the ad into B2 — and a later
    `get_backend().get(key)` then looks for the file in the wrong place and
    reports a missing object for an ad that exists.

    Reading the artefact at the moment it is produced removes the ordering
    dependency entirely, and is the more honest check anyway: verify what you
    just made, with the backend that made it.
    """

    def __init__(self, asset, mp4: bytes | None, local_path):
        self.asset = asset
        self.mp4 = mp4
        self.local_path = local_path

    @property
    def content(self):
        return self.asset.attempts[0].content


@pytest.fixture(scope="module")
def produced():
    """Run the real advertisement track once; every assertion reads this."""
    import time

    from app.pipeline.ad import run_ad_track

    probe_models()
    campaign_id = f"live-ad-{int(time.time())}"

    image = _asset(
        "image",
        AttemptContent(
            image_url=None,  # no approved still needed: every shot makes its own frame
            primary_color="#1E3A2B",
            secondary_color="#F4F1EA",
            accent_color="#D97706",
        ),
    )
    copy = _asset(
        "copy",
        AttemptContent(
            headline="The hour that isn't spoken for",
            call_to_action="Start your first bag",
        ),
    )

    # A REAL voiceover, produced by the real audio track. Passing a stub here
    # would leave the mux — the step that lays sound over the finished cut —
    # unexercised live, and that is precisely the part unit tests can only
    # approximate with synthetic tones.
    from app.pipeline.tracks import run_track

    audio = run_track("audio", BRIEF, campaign_id, Emitter(campaign_id))

    asset = run_ad_track(
        BRIEF, campaign_id, Emitter(campaign_id), image, audio, copy, None
    )
    if asset is None:
        return Produced(None, None, None)

    # Download NOW, while the backend that produced it is still the live one.
    from pathlib import Path

    from app.config import SCRATCH_DIR
    from app.storage.factory import get_backend

    data = None
    local = None
    key = (asset.attempts[0].content.video_url or "").removeprefix("/api/media/")
    if key:
        try:
            data = get_backend().get(key)
            SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
            local = Path(SCRATCH_DIR) / f"{campaign_id}-verify.mp4"
            local.write_bytes(data)
        except Exception as exc:  # noqa: BLE001 - surfaced by the assertions
            print(f"could not download delivered ad: {exc}")

    return Produced(asset, data, local)


@needs_tokenrouter
@needs_b2
@needs_ffmpeg
def test_advertisement_is_produced(produced):
    assert produced.asset is not None, "the advertisement track returned nothing"
    assert produced.asset.status == "passed"
    assert produced.asset.attempts


@needs_tokenrouter
@needs_b2
@needs_ffmpeg
def test_it_is_multi_shot_not_one_still_in_motion(produced):
    """The whole point of the feature."""
    content = produced.content
    shots = content.ad_shots or []
    rendered = [s for s in shots if s.status == "rendered"]

    assert len(rendered) >= 2, f"only {len(rendered)} shot(s) rendered — that is a clip"
    assert content.shot_count == len(rendered)


@needs_tokenrouter
@needs_b2
@needs_ffmpeg
def test_every_shot_is_a_genuinely_different_scene(produced):
    """Distinct prompts AND distinct generated frames — not one image re-used."""
    rendered = [s for s in (produced.content.ad_shots or []) if s.status == "rendered"]

    assert len({s.scene_prompt for s in rendered}) == len(rendered)
    frames = [s.frame_url for s in rendered if s.frame_url]
    assert len(set(frames)) == len(frames), "two shots share a first frame"
    # Each shot was animated separately, so each has its own clip.
    clips = [s.clip_url for s in rendered if s.clip_url]
    assert len(set(clips)) == len(clips)


@needs_tokenrouter
@needs_b2
@needs_ffmpeg
def test_shots_follow_the_advertising_arc(produced):
    rendered = [s for s in (produced.content.ad_shots or []) if s.status == "rendered"]
    roles = [s.role for s in rendered]

    assert roles[0] == "hook", f"an ad opens on a hook, got {roles}"
    assert len(set(roles)) == len(roles), f"duplicate roles: {roles}"
    assert all(r in ("hook", "product", "benefit", "cta") for r in roles)


@needs_tokenrouter
@needs_b2
@needs_ffmpeg
def test_the_delivered_file_is_a_real_cut(produced):
    """Longer than any single shot => concatenation actually happened.

    This is the assertion that would catch the pipeline silently shipping one
    clip while reporting three shots.
    """
    content = produced.content
    rendered = [s for s in (content.ad_shots or []) if s.status == "rendered"]

    duration = content.video_duration_seconds
    assert duration, "no duration could be read from the delivered file"

    longest_single = max(s.duration_seconds for s in rendered)
    assert duration > longest_single + 1, (
        f"delivered film is {duration}s but the longest single shot is "
        f"{longest_single}s — this looks like one clip, not a cut"
    )

    expected = sum(s.duration_seconds for s in rendered)
    assert duration >= expected * 0.6, (
        f"{duration}s is far short of the {expected}s of shots — shots were dropped at concat"
    )


@needs_tokenrouter
@needs_b2
@needs_ffmpeg
def test_the_end_card_was_appended(produced):
    content = produced.content
    assert content.has_end_card is True

    rendered = [s for s in (content.ad_shots or []) if s.status == "rendered"]
    shot_seconds = sum(s.duration_seconds for s in rendered)
    # The film must be LONGER than the shots alone — that extra tail is the card.
    assert (content.video_duration_seconds or 0) > shot_seconds * 0.9


@needs_tokenrouter
@needs_b2
@needs_ffmpeg
def test_the_delivered_file_is_a_real_mp4_with_audio(produced):
    """Inspect the actual delivered bytes, not just the metadata we recorded."""
    content = produced.content

    assert produced.mp4, "the delivered advertisement could not be downloaded"
    assert len(produced.mp4) > 100_000, f"delivered ad is only {len(produced.mp4)} bytes"
    assert produced.mp4[4:8] == b"ftyp", "delivered file is not an MP4 container"

    assert assemble.probe_duration(produced.local_path), "ffmpeg could not read it"

    # The voiceover track ran for real, so the finished ad must carry sound.
    assert content.has_voiceover is True, "the ad was cut without its voiceover"
    assert assemble.has_audio_stream(produced.local_path), (
        "hasVoiceover=True but the delivered file carries no audio stream"
    )


@needs_tokenrouter
@needs_b2
@needs_ffmpeg
def test_the_voiceover_did_not_truncate_the_picture(produced):
    """The `-shortest` trap, verified on a real ad.

    The narration is ~15s and the film is ~20s. If the mux truncated the
    picture to the audio, the end card — the only frame carrying the brand name
    and CTA — would be silently gone.
    """
    content = produced.content
    rendered = [s for s in (content.ad_shots or []) if s.status == "rendered"]
    shot_seconds = sum(s.duration_seconds for s in rendered)

    assert (content.video_duration_seconds or 0) > shot_seconds, (
        "the film is no longer than its shots — the end card was truncated away"
    )


@needs_tokenrouter
@needs_b2
@needs_ffmpeg
def test_every_shot_and_the_final_cut_carry_provenance(produced):
    content = produced.content
    rendered = [s for s in (content.ad_shots or []) if s.status == "rendered"]

    assert content.manifest_hash, "the assembled ad has no manifest"
    assert len(content.manifest_hash) == 64
    for shot in rendered:
        assert shot.manifest_hash, f"shot {shot.index} has no manifest"


@needs_tokenrouter
@needs_b2
@needs_ffmpeg
def test_the_critique_does_not_overstate_what_was_verified(produced):
    """Motion is not scored by any model, and the record must say so."""
    critique = produced.asset.attempts[0].critique

    assert "not independently scored" in critique.suggested_fixes
    structure = next(c for c in critique.criteria if c.name == "Narrative Structure")
    assert structure.passed is True
    assert produced.asset.attempts[0].prompt_used.count("scene:") >= 2
