"""Prompt construction, including the retry rewrite that closes the loop.

The retry prompt is the whole point of the project: attempt N+1 must visibly
incorporate attempt N's critique. build_image_prompt() therefore appends the
critique's suggestedFixes verbatim, and the resulting string is what gets stored
in Attempt.promptUsed and rendered by ProvenanceLog.
"""

from __future__ import annotations

import re

from app.brain.models import CampaignStrategy
from app.domain.models import CampaignBrief, CritiqueResult

# The scoring guidance and the pass threshold MUST agree. An earlier version
# told the model "first drafts rarely exceed 80" while the pass bar was 85,
# which made passing effectively impossible and failed every campaign.
CRITIQUE_SYSTEM = (
    "You are a demanding but FAIR brand art director reviewing generated "
    "campaign assets against a client brief.\n"
    "Scoring calibration (follow it exactly):\n"
    "- 85-95: the asset genuinely satisfies the brief's tone, palette and craft. "
    "This is a PASS. Award it whenever the work meets the brief — do not withhold "
    "a pass from work that is on-brief just to seem rigorous.\n"
    "- 70-84: competent but with at least one clear, nameable miss.\n"
    "- below 70: substantially off-brief.\n"
    "A polished first draft may well score 85+. Revisions that fix the stated "
    "problems should score higher than the attempt they revise.\n"
    "Be specific and actionable — never generic. "
    "Respond ONLY with JSON matching the requested schema."
)


def hex_to_name(hex_code: str) -> str:
    """Describe a hex colour in words.

    Image models cannot interpret hex codes — passing '#1E3A2B' produced images
    the critique correctly failed on palette adherence every time. Converting to
    'deep forest green' is what actually steers the render.
    """
    raw = hex_code.strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    try:
        r, g, b = (int(raw[i : i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return hex_code

    mx, mn = max(r, g, b), min(r, g, b)
    light = (mx + mn) / 2 / 255
    chroma = (mx - mn) / 255

    if chroma < 0.10:
        if light > 0.92:
            return "near-white"
        if light > 0.75:
            return "soft off-white"
        if light > 0.55:
            return "light warm grey"
        if light > 0.3:
            return "mid grey"
        if light > 0.12:
            return "charcoal"
        return "near-black"

    if mx == r:
        hue = 60 * (((g - b) / (mx - mn)) % 6)
    elif mx == g:
        hue = 60 * (((b - r) / (mx - mn)) + 2)
    else:
        hue = 60 * (((r - g) / (mx - mn)) + 4)

    for lo, hi, name in (
        (0, 15, "red"),
        (15, 40, "burnt orange"),
        (40, 52, "amber"),
        (52, 68, "golden yellow"),
        (68, 95, "olive"),
        (95, 160, "green"),
        (160, 195, "teal"),
        (195, 250, "blue"),
        (250, 290, "violet"),
        (290, 330, "magenta"),
        (330, 361, "crimson"),
    ):
        if lo <= hue < hi:
            base = name
            break
    else:
        base = "neutral"

    if light < 0.25:
        qualifier = "deep "
    elif light < 0.45:
        qualifier = "rich "
    elif light > 0.8:
        qualifier = "pale "
    elif light > 0.65:
        qualifier = "soft "
    else:
        qualifier = ""
    if chroma < 0.28 and qualifier in ("", "soft "):
        qualifier = "muted "
    if base == "green" and light < 0.35:
        base = "forest green"
    return f"{qualifier}{base}".strip()


def _palette(brief: CampaignBrief, *, include_hex: bool = True) -> str:
    """Describe the brief's palette.

    include_hex=False for IMAGE prompts. Image models render hex codes as
    literal text: passing "(#1E3A2B)" produced posters with colour swatches
    labelled "E3AB"/"D99" painted into the frame, which the critique then
    correctly failed for containing lettering. Hex is still useful for the
    text-based critique rubric, where nothing gets rendered.
    """
    c = brief.colors
    if not include_hex:
        return (
            f"{hex_to_name(c.primary)} as the dominant colour, "
            f"{hex_to_name(c.secondary)} as the base/background, "
            f"{hex_to_name(c.accent)} as the accent"
        )
    return (
        f"{hex_to_name(c.primary)} ({c.primary}) as the dominant colour, "
        f"{hex_to_name(c.secondary)} ({c.secondary}) as the base/background, "
        f"{hex_to_name(c.accent)} ({c.accent}) as the accent"
    )


def _tone(brief: CampaignBrief) -> str:
    return ", ".join(brief.tone_tags) if brief.tone_tags else "Modern"


def _strategy_block(
    strategy: CampaignStrategy | None, direction_field: str, *, for_image: bool = False
) -> str:
    """Inject the Campaign Brain's strategy into a generation prompt.

    This is what makes the three tracks one campaign instead of three unrelated
    assets: they never see each other's output, so the shared big idea and the
    shared avoid-list are the only things holding them together.

    The `avoid` list matters as much as the direction. It is where the brand's
    accumulated laws actually bite — a rule learned from campaign #1's rejected
    image only changes anything if it reaches campaign #7's prompt.
    """
    if strategy is None:
        return ""

    direction = getattr(strategy, direction_field, "") or ""
    parts = ["CAMPAIGN STRATEGY (from the brand's Campaign Brain)"]
    if strategy.big_idea:
        parts.append(f"Big idea: {strategy.big_idea}")
    if direction:
        parts.append(f"Direction for this asset: {direction}")
    if strategy.avoid:
        parts.append(
            "Do NOT do any of the following — these are rules this brand's own "
            "past rejections established: " + "; ".join(strategy.avoid)
        )

    block = "\n".join(parts)
    # Image models letter hex codes and the word "swatch" straight into the
    # frame, and strategy text is free-form model output that may contain both.
    if for_image:
        block = sanitize_for_image_prompt(block)
    # Separator added AFTER sanitizing: sanitize_for_image_prompt() ends in
    # .strip(), so leading newlines baked into the block would be eaten and the
    # heading would run straight into the previous sentence.
    return f"\n\n{block}"


_HEX_RE = re.compile(r"#?\b[0-9A-Fa-f]{6}\b")
_SWATCH_RE = re.compile(
    r"\b(palette strip|colour strip|color strip|swatch(?:es)?|colour chip|color chip|"
    r"legend|annotation|caption|label(?:s|led|ed)?|hex code[s]?|hex value[s]?)\b",
    re.IGNORECASE,
)


def sanitize_for_image_prompt(text: str) -> str:
    """Strip anything that makes an image model paint text into the frame.

    The retry prompt appends the critique's suggestedFixes verbatim — that is
    the causal link that makes the loop real. But the critique rubric contains
    hex codes, so the critique echoes them back, and seedream then renders
    "#F4F1EA" as literal text next to a colour strip. Observed repeatedly.

    Only the text handed to the IMAGE model is sanitized; the stored
    Attempt.promptUsed keeps the sanitized version too, so what the provenance
    log shows is genuinely what was sent.
    """
    cleaned = _HEX_RE.sub("that colour", text)
    cleaned = _SWATCH_RE.sub("colour treatment", cleaned)
    # Drop any remaining '#'. Critiques write things like "as attempt #1",
    # and a stray hash is exactly the kind of glyph the image model decides to
    # letter into the frame. Nothing downstream needs it.
    cleaned = re.sub(r"#\s*(\d)", r"\1", cleaned)
    cleaned = cleaned.replace("#", "")
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def build_image_prompt(
    brief: CampaignBrief,
    attempt: int,
    critique: CritiqueResult | None,
    strategy: CampaignStrategy | None = None,
) -> str:
    base = (
        f"Premium commercial brand key visual for {brief.brand_name} — "
        f"{brief.product_service}. "
        f"Mood and tone: {_tone(brief)}. "
        # No hex codes here — see _palette(): image models paint them as text.
        f"Colour palette: {_palette(brief, include_hex=False)} — these colours "
        "must clearly dominate. "
        f"Target audience: {brief.target_audience}. "
        "Editorial advertising photography, single clear hero subject, "
        "soft natural directional light, shallow depth of field, "
        "balanced composition with generous negative space for overlaid copy. "
        "This is a photograph of real objects only. Absolutely no text, "
        "lettering, numbers, hex codes, colour swatches, palette strips, charts, "
        "labels, logos or watermarks anywhere in the frame."
    )
    if brief.brief_text.strip():
        base += f" Creative direction: {brief.brief_text.strip()}"
    base += _strategy_block(strategy, "visual_direction", for_image=True)
    if attempt > 1 and critique is not None:
        # This is the retry loop made visible — the art director's notes go
        # straight back into the generation prompt, sanitized so hex codes and
        # swatch language don't get painted into the image.
        base += (
            f"\n\nREVISION {attempt} — the previous attempt scored "
            f"{critique.overall_score}/100 and was rejected. "
            f"Art director's required fixes: "
            f"{sanitize_for_image_prompt(critique.suggested_fixes)} "
            f"Reason for rejection: {sanitize_for_image_prompt(critique.reasoning)} "
            "Apply these as photographic art direction only — still a clean "
            "photograph with no text, numbers, swatches or palette strips."
        )
    return base


def build_copy_prompt(
    brief: CampaignBrief,
    attempt: int,
    critique: CritiqueResult | None,
    strategy: CampaignStrategy | None = None,
) -> str:
    base = (
        f"Write a marketing copy suite for {brief.brand_name}, which offers "
        f"{brief.product_service}. Audience: {brief.target_audience}. "
        f"Required tone: {_tone(brief)}. "
        f"Brief: {brief.brief_text or 'n/a'}. "
        "Avoid generic startup buzzwords (revolutionary, game-changing, seamless, "
        "elevate, unlock). Write like a real brand with a point of view."
    )
    base += _strategy_block(strategy, "copy_angle")
    if attempt > 1 and critique is not None:
        base += (
            f"\n\nREVISION {attempt} — the previous copy scored "
            f"{critique.overall_score}/100. Required fixes: {critique.suggested_fixes}"
        )
    return base


def build_voiceover_prompt(
    brief: CampaignBrief,
    attempt: int,
    critique: CritiqueResult | None,
    strategy: CampaignStrategy | None = None,
) -> str:
    base = (
        f"Write a spoken voiceover script for a short {brief.brand_name} brand film. "
        f"Product: {brief.product_service}. Audience: {brief.target_audience}. "
        f"Tone: {_tone(brief)}. "
        "It must be 35-55 words, read aloud in about 15 seconds, written for the ear "
        "rather than the page. No stage directions, no speaker labels. "
        "Also describe the ideal voice in a short phrase."
    )
    base += _strategy_block(strategy, "voice_direction")
    if attempt > 1 and critique is not None:
        base += (
            f"\n\nREVISION {attempt} — previous script scored "
            f"{critique.overall_score}/100. Required fixes: {critique.suggested_fixes}"
        )
    return base


def build_video_prompt(
    brief: CampaignBrief, strategy: CampaignStrategy | None = None
) -> str:
    """Motion direction for animating the approved key visual.

    The still already carries the approved composition and palette, so this
    describes CAMERA and MOTION only. Asking for new subject matter would let
    the model redraw the scene and discard what passed critique.

    The strategy's big idea is passed as MOOD only, for the same reason: the
    frame it animates already passed critique, and re-describing the scene from
    strategy would invite the model to redraw it.
    """
    mood = ""
    if strategy is not None and strategy.big_idea:
        mood = sanitize_for_image_prompt(
            f" The campaign's big idea, for emotional register only — do not "
            f"add or change any objects to express it: {strategy.big_idea}"
        )
    return (
        f"Cinematic brand film for {brief.brand_name} — {brief.product_service}. "
        f"Mood: {_tone(brief)}. "
        "Animate this still with restrained, premium motion: a slow push-in, "
        "gentle parallax, and soft drifting natural light. "
        "Keep the existing composition, subject and colour palette exactly as "
        "they are — do not add, remove or redesign any objects. "
        "No text, lettering, captions, logos or watermarks. "
        "Steady camera, no whip pans, no fast cuts, no people entering frame."
        + mood
    )


def image_rubric(brief: CampaignBrief, attempt: int) -> str:
    return (
        f"Evaluate this generated campaign image for {brief.brand_name} "
        f"({brief.product_service}).\n\n"
        f"BRIEF REQUIREMENTS\n"
        f"- Required mood/tone: {_tone(brief)}\n"
        f"- Required palette: {_palette(brief)}\n"
        f"- Target audience: {brief.target_audience}\n"
        f"- Creative direction: {brief.brief_text or 'n/a'}\n"
        f"- This is attempt #{attempt}.\n\n"
        "Score these three criteria 0-100: 'Tone Match' (target 85), "
        "'Brand Consistency' (target 80, i.e. does the palette actually match), "
        "'Technical Clarity' (target 80, composition/artefacts/usability as an ad). "
        "Set overallScore as your weighted judgement. The pass bar is 85: if this "
        "image would be acceptable to ship as a campaign key visual for this "
        "brief, score it 85 or above. "
        "The image must be a clean photograph of real objects: penalise any "
        "text, numbers, colour swatches, palette strips or labels rendered into "
        "the frame under Technical Clarity. "
        "In suggestedFixes, give concrete art direction that could be appended "
        "to an image-generation prompt — describe colours in WORDS only, never "
        "as hex codes, and never suggest adding swatches, palette strips, "
        "captions or any other lettering to the image. "
        "If this is attempt #2 or later, judge the image on its own merits — "
        "reward genuine improvement rather than anchoring to earlier attempts."
    )


# The critique cannot see the generation schema, so without this it invents
# structural rules ("should have 3 social posts, 5 bullets") that contradict the
# actual contract and fails correct output on Technical Clarity forever.
_STRUCTURE_NOTE = {
    "marketing copy": (
        "REQUIRED STRUCTURE (this is the agreed contract — output matching it is "
        "CORRECT, do not penalise it): exactly one headline, one subheadline, one "
        "bodyText, one callToAction, exactly 3 keyBenefitBullets, and exactly 2 "
        "socialPosts. Judge the WRITING QUALITY and tone fit, not the number of "
        "items. Only flag a structural problem if a field is empty, or if a single "
        "string obviously contains several concatenated items."
    ),
    "voiceover script": (
        "REQUIRED STRUCTURE: a single spoken script of roughly 35-55 words with no "
        "stage directions or speaker labels, plus a short voice description. "
        "Output matching that is CORRECT — judge how it sounds read aloud."
    ),
}


def text_rubric(brief: CampaignBrief, attempt: int, kind: str, content: str) -> str:
    return (
        f"Evaluate this generated {kind} for {brief.brand_name} "
        f"({brief.product_service}).\n\n"
        f"BRIEF REQUIREMENTS\n"
        f"- Required tone: {_tone(brief)}\n"
        f"- Target audience: {brief.target_audience}\n"
        f"- Creative direction: {brief.brief_text or 'n/a'}\n"
        f"- This is attempt #{attempt}.\n\n"
        f"{_STRUCTURE_NOTE.get(kind, '')}\n\n"
        f"CONTENT UNDER REVIEW\n{content}\n\n"
        "Score these three criteria 0-100: 'Tone Match' (target 85), "
        "'Brand Consistency' (target 80), 'Technical Clarity' (target 80). "
        "The pass bar is 85: if this copy would be acceptable to ship for this "
        "brief, score it 85 or above. In suggestedFixes give concrete, "
        "actionable rewrite instructions."
    )
