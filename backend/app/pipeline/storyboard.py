"""Storyboard: the difference between an advertisement and a moving photograph.

The previous brand film animated the one approved key visual — a slow push-in on
a still. That reads as a motion test, not a commercial. A commercial has
structure: it earns attention, shows the thing, gives you a reason, then asks
for something.

So before any pixels are generated, an LLM writes a real shot list against the
campaign's own strategy, copy and voiceover. Each shot gets:

  * its own SCENE — a distinct, photographable moment, not a re-crop
  * its own CAMERA MOVE — chosen to suit that scene
  * its own LINE of the narration, so picture and voice are cut together

The narration is split across shots rather than written fresh, because the
voiceover has already been generated, critiqued and (in the live suite)
transcription-verified. Rewriting it here would throw away work that passed.
"""

from __future__ import annotations

import logging
from typing import Any

from app.brain.llm import brain_call
from app.brain.models import CampaignStrategy
from app.domain.models import AdShot, CampaignBrief
from app.domain.prompts import hex_to_name, sanitize_for_image_prompt

logger = logging.getLogger(__name__)

_VALID_ROLES = ("hook", "product", "benefit", "cta")

STORYBOARD_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "AdStoryboard",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["shots"],
            "properties": {
                "shots": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "role",
                            "title",
                            "scenePrompt",
                            "motionPrompt",
                            "voiceoverLine",
                        ],
                        "properties": {
                            "role": {"type": "string", "enum": list(_VALID_ROLES)},
                            "title": {"type": "string"},
                            "scenePrompt": {"type": "string"},
                            "motionPrompt": {"type": "string"},
                            "voiceoverLine": {"type": "string"},
                        },
                    },
                }
            },
        },
    },
}


def _strategy_block(strategy: CampaignStrategy | None) -> str:
    if strategy is None:
        return ""
    lines = ["CAMPAIGN STRATEGY (every shot must serve this):"]
    if strategy.big_idea:
        lines.append(f"  big idea: {strategy.big_idea}")
    if strategy.visual_direction:
        lines.append(f"  visual direction: {strategy.visual_direction}")
    if strategy.avoid:
        lines.append("  never: " + "; ".join(strategy.avoid))
    return "\n".join(lines) + "\n"


def storyboard_prompt(
    brief: CampaignBrief,
    strategy: CampaignStrategy | None,
    voiceover_script: str,
    approved_visual_description: str,
    shot_count: int,
    seconds_per_shot: int,
) -> str:
    colors = brief.colors
    palette = (
        f"{hex_to_name(colors.primary)} dominant, "
        f"{hex_to_name(colors.secondary)} base, "
        f"{hex_to_name(colors.accent)} accent"
    )

    return f"""Write the shot list for a {shot_count * seconds_per_shot}-second
television-grade advertisement for {brief.brand_name}.

BRAND: {brief.brand_name} — {brief.product_service}
AUDIENCE: {brief.target_audience}
TONE: {', '.join(brief.tone_tags) or 'Modern'}
PALETTE: {palette}
BRIEF: {brief.brief_text or '(none supplied)'}

{_strategy_block(strategy)}
THE APPROVED KEY VISUAL (already passed art-direction critique — the film must
look like it belongs to the same campaign):
  {approved_visual_description}

THE VOICEOVER THAT WILL PLAY OVER THIS FILM, already recorded:
  "{voiceover_script}"

Produce exactly {shot_count} shots, each {seconds_per_shot} seconds, in this
narrative order:
  1. hook     — earn attention in the first second. A moment, not a product.
  2. product  — the thing itself, unmistakably and attractively.
  3. benefit  — what changes for the person. Show the outcome, not the object.
  {'4. cta      — the closing image the end card lands on.' if shot_count >= 4 else ''}

For each shot:

- title: three or four words a director would put on a storyboard card.

- scenePrompt: describe ONE photographable frame. This becomes the shot's first
  frame, so it must be a still image description: subject, setting, lighting,
  camera distance, composition. Every shot must be a DIFFERENT scene — different
  subject or setting or framing. Do not describe the same table from four
  angles. Carry the palette and lighting quality of the approved key visual so
  the shots cut together as one film.
  Absolutely no text, lettering, numbers, logos, captions or watermarks in
  frame — those are added later and generated ones come out malformed.

- motionPrompt: the camera move for these {seconds_per_shot} seconds, chosen for
  this shot. Vary it across the film — a slow push-in, a gentle parallax drift,
  a rack focus, a slow tilt. Restrained and premium; no whip pans, no fast cuts
  inside a shot, nobody walking into frame. Describe the CAMERA, never new
  objects, because the first frame is fixed and the model will distort anything
  you ask it to add.

- voiceoverLine: the portion of the recorded narration above that plays over
  this shot. Split the script across the shots IN ORDER and use its exact words
  — do not rewrite, add or invent narration. If the script runs out, leave the
  remaining shots' lines empty.

The film has to work with the sound off. Constraints: no platitudes, nothing
that could belong to any other brand, and no claim the brief does not support."""


def build_storyboard(
    brief: CampaignBrief,
    *,
    campaign_id: str,
    strategy: CampaignStrategy | None,
    voiceover_script: str,
    approved_visual_description: str,
    shot_count: int,
    seconds_per_shot: int,
) -> tuple[list[AdShot], str | None]:
    """Write the shot list. Returns ([], None) on failure — never raises.

    Reuses brain_call for the same reasons the lobes do: one provenance
    manifest per creative decision, and one response_format degradation ladder
    rather than a second copy of it.
    """
    parsed, manifest = brain_call(
        "storyboard",
        campaign_id=campaign_id,
        prompt=storyboard_prompt(
            brief,
            strategy,
            voiceover_script,
            approved_visual_description,
            shot_count,
            seconds_per_shot,
        ),
        schema=STORYBOARD_SCHEMA,
        temperature=0.8,
        max_tokens=2000,
    )
    if not parsed:
        return [], None

    shots = _coerce_shots(parsed, shot_count, seconds_per_shot)
    # Fewer than two distinct scenes is not an advertisement, and falling back
    # to the single-still film is better than shipping a degenerate cut.
    if len(shots) < 2:
        logger.warning("storyboard returned %d usable shots; rejecting", len(shots))
        return [], manifest
    return shots, manifest


def _coerce_shots(
    parsed: dict[str, Any], shot_count: int, seconds_per_shot: int
) -> list[AdShot]:
    shots: list[AdShot] = []
    for i, raw in enumerate(parsed.get("shots") or []):
        if not isinstance(raw, dict):
            continue
        scene = str(raw.get("scenePrompt") or "").strip()
        if not scene:
            continue

        role = str(raw.get("role") or "").strip().lower()
        if role not in _VALID_ROLES:
            # Positional default rather than dropping the shot: the ordering
            # already carries the narrative, and a mislabelled shot still cuts.
            role = _VALID_ROLES[min(i, len(_VALID_ROLES) - 1)]

        shots.append(
            AdShot(
                index=len(shots),
                role=role,  # type: ignore[arg-type]
                title=str(raw.get("title") or f"Shot {len(shots) + 1}").strip(),
                # Sanitized here, not at render time: these strings go straight
                # to an image model, which letters hex codes and the word
                # "swatch" into the frame given the chance.
                scene_prompt=sanitize_for_image_prompt(scene),
                motion_prompt=sanitize_for_image_prompt(
                    str(raw.get("motionPrompt") or "slow, restrained push-in").strip()
                ),
                duration_seconds=seconds_per_shot,
                voiceover_line=str(raw.get("voiceoverLine") or "").strip(),
            )
        )
        if len(shots) >= shot_count:
            break
    return shots


def fallback_storyboard(
    brief: CampaignBrief, shot_count: int, seconds_per_shot: int
) -> list[AdShot]:
    """A structurally valid ad when the storyboard model is unreachable.

    Deliberately generic in its wording but still MULTI-SHOT: the point of the
    feature is that the film cuts between scenes, and losing the LLM should cost
    us the writing, not the format.
    """
    product = brief.product_service
    tone = ", ".join(brief.tone_tags) or "modern"
    palette = (
        f"{hex_to_name(brief.colors.primary)} dominant with a restrained "
        f"{hex_to_name(brief.colors.accent)} accent"
    )
    base = (
        f"Editorial advertising photography, {tone} mood, {palette}, "
        "soft natural directional light, shallow depth of field, "
        "no text or lettering anywhere in frame. "
    )

    blueprint = [
        ("hook", "Opening Moment", f"An evocative wide establishing scene suggesting {product}, generous negative space. "),
        ("product", "The Product", f"A close, tactile hero shot of {product} as the clear single subject. "),
        ("benefit", "The Payoff", f"A person's hands or point of view enjoying the result of {product}, warm and unhurried. "),
        ("cta", "Closing Frame", f"A calm, uncluttered final composition of {product} with room for a closing title. "),
    ]
    motions = [
        "slow push-in",
        "gentle parallax drift across the subject",
        "slow tilt with a soft rack focus",
        "almost imperceptible push-in, settling to still",
    ]

    return [
        AdShot(
            index=i,
            role=role,  # type: ignore[arg-type]
            title=title,
            scene_prompt=sanitize_for_image_prompt(base + scene),
            motion_prompt=motions[i],
            duration_seconds=seconds_per_shot,
        )
        for i, (role, title, scene) in enumerate(blueprint[:shot_count])
    ]
