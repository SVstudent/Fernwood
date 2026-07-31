"""Prompt construction, including the retry rewrite that closes the loop.

The retry prompt is the whole point of the project: attempt N+1 must visibly
incorporate attempt N's critique. build_image_prompt() therefore appends the
critique's suggestedFixes verbatim, and the resulting string is what gets stored
in Attempt.promptUsed and rendered by ProvenanceLog.
"""

from __future__ import annotations

from app.domain.models import CampaignBrief, CritiqueResult

CRITIQUE_SYSTEM = (
    "You are a demanding brand art director reviewing generated campaign assets "
    "against a client brief. You are hard to please: first drafts rarely exceed "
    "80/100, and you only award 85+ when tone, palette and craft are all clearly "
    "on-brief. Be specific and actionable — never generic. "
    "Respond ONLY with JSON matching the requested schema."
)


def _palette(brief: CampaignBrief) -> str:
    c = brief.colors
    return f"primary {c.primary}, secondary {c.secondary}, accent {c.accent}"


def _tone(brief: CampaignBrief) -> str:
    return ", ".join(brief.tone_tags) if brief.tone_tags else "Modern"


def build_image_prompt(
    brief: CampaignBrief, attempt: int, critique: CritiqueResult | None
) -> str:
    base = (
        f"Commercial brand key visual for {brief.brand_name} — {brief.product_service}. "
        f"Mood and tone: {_tone(brief)}. "
        f"Colour palette: {_palette(brief)}. "
        f"Target audience: {brief.target_audience}. "
        "Editorial advertising photography, balanced composition, "
        "generous negative space for overlaid copy, no text or lettering in the image."
    )
    if brief.brief_text.strip():
        base += f" Creative direction: {brief.brief_text.strip()}"
    if attempt > 1 and critique is not None:
        # This is the retry loop made visible — the art director's notes go
        # straight back into the generation prompt.
        base += (
            f"\n\nREVISION {attempt} — the previous attempt scored "
            f"{critique.overall_score}/100 and was rejected. "
            f"Art director's required fixes: {critique.suggested_fixes} "
            f"Reason for rejection: {critique.reasoning}"
        )
    return base


def build_copy_prompt(
    brief: CampaignBrief, attempt: int, critique: CritiqueResult | None
) -> str:
    base = (
        f"Write a marketing copy suite for {brief.brand_name}, which offers "
        f"{brief.product_service}. Audience: {brief.target_audience}. "
        f"Required tone: {_tone(brief)}. "
        f"Brief: {brief.brief_text or 'n/a'}. "
        "Avoid generic startup buzzwords (revolutionary, game-changing, seamless, "
        "elevate, unlock). Write like a real brand with a point of view."
    )
    if attempt > 1 and critique is not None:
        base += (
            f"\n\nREVISION {attempt} — the previous copy scored "
            f"{critique.overall_score}/100. Required fixes: {critique.suggested_fixes}"
        )
    return base


def build_voiceover_prompt(
    brief: CampaignBrief, attempt: int, critique: CritiqueResult | None
) -> str:
    base = (
        f"Write a spoken voiceover script for a short {brief.brand_name} brand film. "
        f"Product: {brief.product_service}. Audience: {brief.target_audience}. "
        f"Tone: {_tone(brief)}. "
        "It must be 35-55 words, read aloud in about 15 seconds, written for the ear "
        "rather than the page. No stage directions, no speaker labels. "
        "Also describe the ideal voice in a short phrase."
    )
    if attempt > 1 and critique is not None:
        base += (
            f"\n\nREVISION {attempt} — previous script scored "
            f"{critique.overall_score}/100. Required fixes: {critique.suggested_fixes}"
        )
    return base


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
        "Set overallScore as your weighted judgement, and passed=true only if "
        "overallScore >= 85. In suggestedFixes, give concrete art direction that "
        "could be appended to an image-generation prompt to fix the problems."
    )


def text_rubric(brief: CampaignBrief, attempt: int, kind: str, content: str) -> str:
    return (
        f"Evaluate this generated {kind} for {brief.brand_name} "
        f"({brief.product_service}).\n\n"
        f"BRIEF REQUIREMENTS\n"
        f"- Required tone: {_tone(brief)}\n"
        f"- Target audience: {brief.target_audience}\n"
        f"- Creative direction: {brief.brief_text or 'n/a'}\n"
        f"- This is attempt #{attempt}.\n\n"
        f"CONTENT UNDER REVIEW\n{content}\n\n"
        "Score these three criteria 0-100: 'Tone Match' (target 85), "
        "'Brand Consistency' (target 80), 'Technical Clarity' (target 80). "
        "Set passed=true only if overallScore >= 85. In suggestedFixes give "
        "concrete, actionable rewrite instructions."
    )
