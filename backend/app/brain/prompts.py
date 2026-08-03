"""Prompt construction for the five lobes.

Separated from lobes.py so the control flow there stays readable, and because
these strings are the actual product surface — the difference between a brain
that reasons and a brain that produces horoscopes is almost entirely here.

Two recurring techniques:

  * Laws are injected WITH their evidence, not as bare assertions. A model told
    "avoid literal coffee cups (learned when attempt #1 of camp-1712 scored
    58/100: 'the cup dominates and reads as stock photography')" applies the
    rule far more faithfully than one told the rule alone.
  * Every lobe is told what it may not do. Left unconstrained, LLMs answer
    creative-strategy prompts with confident, generic filler; naming the
    failure mode is what keeps the output specific to this brief.
"""

from __future__ import annotations

from typing import Any

from app.brain.models import BrandLaw, CampaignStrategy, Persona
from app.domain.models import Campaign, CampaignBrief


def _brief_block(brief: CampaignBrief) -> str:
    return (
        f"BRAND: {brief.brand_name}\n"
        f"PRODUCT / SERVICE: {brief.product_service}\n"
        f"TARGET AUDIENCE: {brief.target_audience}\n"
        f"TONE: {', '.join(brief.tone_tags) or 'unspecified'}\n"
        f"PALETTE: primary {brief.colors.primary}, secondary {brief.colors.secondary}, "
        f"accent {brief.colors.accent}\n"
        f"BRIEF: {brief.brief_text or '(none supplied)'}"
    )


def _laws_block(laws: list[BrandLaw]) -> str:
    if not laws:
        return (
            "LEARNED BRAND LAWS: none. This is the first campaign for this brand — "
            "you have no memory to draw on. Do not pretend otherwise."
        )
    lines = [f"LEARNED BRAND LAWS ({len(laws)}, strongest first):"]
    for law in laws:
        lines.append(
            f"  [{law.id}] ({law.category}, confidence {law.confidence}, "
            f"reinforced {law.reinforced_count}x) {law.text}\n"
            f"        evidence: {law.evidence}"
        )
    return "\n".join(lines)


# ------------------------------------------------------------------ strategy
def strategy_prompt(brief: CampaignBrief, laws: list[BrandLaw]) -> str:
    return f"""Write the campaign strategy that three separate generators (a key
visual, a voiceover, and a marketing copy suite) will each be aimed with. They
never see each other's output, so this strategy is the ONLY thing that makes
them feel like one campaign.

{_brief_block(brief)}

{_laws_block(laws)}

Produce:
- bigIdea: the single creative thought this campaign is built on. One sentence,
  concrete enough that two different designers would produce recognisably
  related work from it. Not a slogan.
- positioning: what this brand is claiming relative to its alternatives, in the
  target audience's own terms.
- visualDirection: composition, subject, lighting and palette guidance for the
  key visual. Reference the palette above by role, not by hex code.
- voiceDirection: how the voiceover should sound — pacing, register, the
  posture it takes toward the listener.
- copyAngle: the argument the copy makes, and the objection it pre-empts.
- avoid: 2-6 specific anti-patterns. Every learned law above that rules
  something out MUST appear here in applicable form.

Constraints: no marketing platitudes ("elevate", "unleash", "game-changing").
Everything must be specific to THIS brief. If the learned laws contradict the
brief, follow the brief and note the tension in positioning."""


# ----------------------------------------------------------------- foresight
def foresight_prompt(
    brief: CampaignBrief,
    laws: list[BrandLaw],
    strategy: CampaignStrategy | None,
    history_note: str,
    pass_threshold: int,
) -> str:
    strategy_block = (
        f"STRATEGY ABOUT TO BE EXECUTED:\n"
        f"  big idea: {strategy.big_idea}\n"
        f"  visual: {strategy.visual_direction}\n"
        f"  voice: {strategy.voice_direction}\n"
        f"  copy: {strategy.copy_angle}\n"
        f"  avoiding: {'; '.join(strategy.avoid)}"
        if strategy
        else "STRATEGY: none was produced — the tracks will run on the brief alone."
    )

    return f"""Predict how this campaign is about to go, BEFORE any generation
quota is spent. You will be scored on this afterwards against the real result,
so calibration matters more than optimism.

{_brief_block(brief)}

{strategy_block}

{_laws_block(laws)}

{history_note}

A vision model will critique the key visual and a text model will critique the
copy and voiceover, each scored 0-100 against this brief's own tone and palette.
Anything below {pass_threshold} is rejected and regenerated with the critique's
feedback folded into the prompt, up to 3 attempts per asset.

Produce:
- predictedScore: the average critique score you expect across all three assets.
- predictedRetries: total regenerations you expect across all three tracks.
- likelyFailureMode: the SPECIFIC thing you expect the critic to object to
  first. Name a concrete flaw ("the palette's accent will dominate the frame
  and read as garish at thumbnail size"), never a category ("tone issues").
- confidence: 0-100. Be honest — with no learned laws, low confidence is the
  correct answer.
- rationale: one or two sentences on what drove the prediction. If prior
  campaigns inform it, say which pattern."""


# ------------------------------------------------------------------ personas
def personas_prompt(brief: CampaignBrief) -> str:
    return f"""Construct a 4-person panel drawn from this campaign's stated
target audience. They will review the finished campaign and their reactions are
the closest thing this studio has to market research, so they have to be people
rather than demographic averages.

{_brief_block(brief)}

Build exactly 4 personas who genuinely sit inside "{brief.target_audience}" —
not four variations of the same enthusiastic buyer. Cover a real spread:

- one who is close to the ideal customer and predisposed to like this
- one who fits the demographic but is tired of being marketed to in this category
- one with a specific practical constraint (budget, time, access, scepticism
  about the claim) that this product has to survive
- one who is adjacent — could be won, currently indifferent

For each: name, age, occupation, location, mindset (one sentence on what they
actually want and what they distrust), skepticism 0-100, and mediaDiet (where
they encounter brands like this).

Constraints: no personas named after the brand. No one whose entire mindset is
"loves quality products". Skepticism must vary by at least 40 points across the
panel — a panel that agrees measures nothing."""


# ----------------------------------------------------------------- reactions
def reactions_prompt(
    brief: CampaignBrief,
    personas: list[Persona],
    campaign: Campaign,
    visual_description: str,
) -> str:
    panel = "\n".join(
        f"  - {p.name}, {p.age}, {p.occupation} ({p.location}). "
        f"Skepticism {p.skepticism}/100. {p.mindset} Media: {p.media_diet}"
        for p in personas
    )

    copy_asset = campaign.assets.copy
    audio_asset = campaign.assets.audio
    copy_content = _approved_content(copy_asset)
    audio_content = _approved_content(audio_asset)

    copy_block = "MARKETING COPY: not produced."
    if copy_content:
        bullets = "; ".join(copy_content.key_benefit_bullets or [])
        socials = " | ".join(copy_content.social_posts or [])
        copy_block = (
            f"MARKETING COPY:\n"
            f"  headline: {copy_content.headline}\n"
            f"  subheadline: {copy_content.subheadline}\n"
            f"  body: {copy_content.body_text}\n"
            f"  call to action: {copy_content.call_to_action}\n"
            f"  benefit bullets: {bullets}\n"
            f"  social posts: {socials}"
        )

    audio_block = "VOICEOVER: not produced."
    if audio_content and audio_content.audio_script:
        audio_block = (
            f"VOICEOVER SCRIPT (spoken, ~{audio_content.duration_seconds or '?'}s):\n"
            f"  {audio_content.audio_script}"
        )

    return f"""React to this finished campaign as each member of the panel. Give
the reaction the real person would have while scrolling, not the reaction a
focus-group participant performs for a moderator.

{_brief_block(brief)}

PANEL:
{panel}

--- THE CAMPAIGN AS THEY ENCOUNTER IT ---

KEY VISUAL, as described by the vision model that critiqued it:
  {visual_description}

{copy_block}

{audio_block}

--- END CAMPAIGN ---

For every panel member produce: personaName (exactly as listed above),
sentiment 0-100, verdict (loves/likes/indifferent/dislikes), quote, objection,
wouldAct 0-100, attentionSeconds.

The quote is the most important field: write the sentence that person would
actually say to a friend about this ad. In their register, not yours. It may be
dismissive. "I genuinely could not tell you what they sell" is a valid and
useful reaction.

objection: the single thing most likely to stop them acting, even from someone
who likes it. An empty objection is almost never true.

attentionSeconds: how long they look before moving on. Most advertising gets
under 2 seconds; be realistic rather than flattering.

Scores must track the persona's stated skepticism — a 90-skepticism reviewer
returning sentiment 88 needs to be justified by something specific in the work.
Then give the panel's consensus and its single topObjection."""


# ------------------------------------------------------------------ learning
def learning_prompt(
    brief: CampaignBrief,
    campaign: Campaign,
    existing_laws: list[BrandLaw],
    rejection_block: str,
    audience_block: str,
) -> str:
    return f"""Extract what this campaign taught you about this specific brand.
You are writing to your future self, which will run the next campaign for
{brief.brand_name} with no other memory of this one.

{_brief_block(brief)}

--- WHAT THE CRITIC REJECTED THIS RUN ---
{rejection_block}

--- HOW THE AUDIENCE PANEL REACTED ---
{audience_block}

{_laws_block(existing_laws)}

Produce up to 4 newLaws. A law qualifies only if ALL of these hold:
  1. It is actionable at generation time — it changes a prompt, not a mood.
     "Warmth matters" is useless. "Warmth must come from lighting temperature,
     not from adding orange to the palette" is a law.
  2. It is specific to {brief.brand_name}, not general advertising advice. If it
     would apply equally to a bank and a bakery, discard it.
  3. It is supported by the evidence above. Quote the critique or the audience
     objection that produced it in the evidence field. Do NOT invent evidence.
  4. It is not already covered by an existing law.

Returning zero new laws is a correct and expected answer when the run surfaced
nothing durable. Do not pad.

Then list reinforcedLawIds: the ids of existing laws this run independently
confirmed. Only include a law if something in the evidence above actually
supports it again — reinforcement raises a law's influence over future
campaigns, so a false one is more expensive than a missed one.

Finally, summary: one sentence a brand manager would find worth reading, on what
this campaign revealed about the brand."""


# ------------------------------------------------------------------ helpers
def _approved_content(asset: Any) -> Any:
    """The content of the attempt that was approved, else the best-scoring one."""
    if asset is None or not asset.attempts:
        return None
    approved = next(
        (a for a in asset.attempts if a.id == asset.final_approved_attempt_id),
        None,
    )
    if approved is None:
        approved = max(asset.attempts, key=lambda a: a.critique.overall_score)
    return approved.content


def rejection_block(campaign: Campaign) -> str:
    """Every rejected attempt this run, with the critique that killed it.

    This is the corpus the Learning lobe reasons over, and it is the reason the
    project stores rejected work rather than overwriting it: the failures carry
    more signal about a brand's boundaries than the successes do.
    """
    lines: list[str] = []
    for track in ("image", "audio", "copy"):
        asset = getattr(campaign.assets, track, None)
        if not asset:
            continue
        for attempt in asset.attempts:
            if attempt.critique_verdict != "FAIL":
                continue
            lines.append(
                f"[{track} attempt #{attempt.attempt_number}, id {attempt.id}] "
                f"scored {attempt.critique.overall_score}/100 — "
                f"{attempt.critique.reasoning} "
                f"Fixes demanded: {attempt.critique.suggested_fixes}"
            )
    if not lines:
        return (
            "Nothing was rejected this run — every asset passed on its first "
            "attempt. That is itself informative: the current laws are holding."
        )
    return "\n".join(lines)
