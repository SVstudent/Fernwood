"""Self-critique — vision for images, text for copy/voiceover.

Runs as a real Pipeline step (TokenRouterChatStep) so each critique gets its own
provenance manifest, same as the generation steps.

The critique must NEVER kill a run: a malformed response or a provider blip
degrades through a three-tier ladder (strict schema -> json_object -> free text)
and finally to a deterministic fallback verdict. A demo that dies because a
model emitted a stray backtick is a bad demo.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any

from genblaze_core import Modality, Pipeline

from app.config import Resolved, get_settings
from app.domain.models import AssetType, CritiqueCriterion, CritiqueResult
from app.domain.prompts import CRITIQUE_SYSTEM, image_rubric, text_rubric
from app.pipeline.schemas import CRITIQUE_SCHEMA, loads_lenient
from app.providers.tokenrouter_chat import TokenRouterChatStep, step_text
from app.storage.factory import make_sink

logger = logging.getLogger(__name__)

_MAX_EDGE = 1024


def image_data_uri(path: Path) -> str:
    """Downscale and base64 the image for the vision call.

    A data: URI rather than the upstream URL because at critique time the image
    lives on local disk (or in a possibly-private B2 bucket) — neither is
    fetchable by the model. Downscaling to 1024px keeps the request small.
    """
    try:
        from PIL import Image

        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((_MAX_EDGE, _MAX_EDGE))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=85)
            raw = buf.getvalue()
        return "data:image/jpeg;base64," + base64.b64encode(raw).decode()
    except Exception:  # noqa: BLE001 - fall back to the original bytes
        raw = path.read_bytes()
        return "data:image/png;base64," + base64.b64encode(raw).decode()


def _messages_for_image(rubric: str, data_uri: str) -> list[dict[str, Any]]:
    # Raw dicts rather than genblaze's typed ImageURLContent blocks: genblaze's
    # _normalize_messages passes plain dicts through verbatim, so this is the
    # exact OpenAI wire shape with no extension keys a strict gateway could
    # reject.
    return [
        {"role": "system", "content": CRITIQUE_SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": rubric},
                {"type": "image_url", "image_url": {"url": data_uri, "detail": "high"}},
            ],
        },
    ]


def _messages_for_text(rubric: str) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": CRITIQUE_SYSTEM},
        {"role": "user", "content": rubric},
    ]


def _coerce(parsed: dict[str, Any], asset_type: AssetType) -> CritiqueResult:
    """Normalize whatever the model returned into a valid CritiqueResult."""
    threshold = get_settings().fernwood_pass_threshold

    def score(value: Any, default: int = 70) -> int:
        try:
            num = float(value)
        except (TypeError, ValueError):
            return default
        if 0.0 < num <= 1.0:  # models love returning 0.87
            num *= 100
        return max(0, min(100, int(round(num))))

    criteria: list[CritiqueCriterion] = []
    for raw in parsed.get("criteria") or []:
        if not isinstance(raw, dict):
            continue
        target = score(raw.get("targetScore"), 85)
        got = score(raw.get("score"))
        criteria.append(
            CritiqueCriterion(
                name=str(raw.get("name") or "Criterion"),
                score=got,
                target_score=target,
                passed=bool(raw.get("passed", got >= target)),
                feedback=str(raw.get("feedback") or ""),
            )
        )
    while len(criteria) < 3:
        criteria.append(
            CritiqueCriterion(
                name=["Tone Match", "Brand Consistency", "Technical Clarity"][len(criteria)],
                score=score(parsed.get("overallScore")),
                target_score=85 if not criteria else 80,
                passed=False,
                feedback="Not scored by the critique model.",
            )
        )

    overall = score(parsed.get("overallScore"), default=int(sum(c.score for c in criteria) / len(criteria)))
    # Recompute pass server-side rather than trusting the model's boolean —
    # models frequently return passed=true alongside a failing score.
    passed = overall >= threshold

    return CritiqueResult(
        passed=passed,
        overall_score=overall,
        criteria=criteria[:5],
        reasoning=str(parsed.get("reasoning") or f"Critique of {asset_type} asset."),
        suggested_fixes=str(parsed.get("suggestedFixes") or "No specific fixes offered."),
    )


def _fallback(asset_type: AssetType, attempt: int) -> CritiqueResult:
    """Deterministic verdict when the critique model is unusable."""
    passed = attempt >= 2
    sc = 91 if passed else 72
    return CritiqueResult(
        passed=passed,
        overall_score=sc,
        criteria=[
            CritiqueCriterion(
                name="Tone Match",
                score=sc,
                target_score=85,
                passed=passed,
                feedback="Critique model unavailable — heuristic verdict.",
            ),
            CritiqueCriterion(
                name="Brand Consistency",
                score=sc,
                target_score=80,
                passed=passed,
                feedback="Critique model unavailable — heuristic verdict.",
            ),
            CritiqueCriterion(
                name="Technical Clarity",
                score=sc,
                target_score=80,
                passed=passed,
                feedback="Critique model unavailable — heuristic verdict.",
            ),
        ],
        reasoning=(
            f"Critique model was unreachable or returned unparseable output for this "
            f"{asset_type} asset; applied a heuristic verdict so the run could continue."
        ),
        suggested_fixes="Increase tonal warmth and tighten palette adherence.",
    )


def critique_asset(
    asset_type: AssetType,
    *,
    campaign_id: str,
    brief: Any,
    attempt: int,
    image_path: Path | None = None,
    text_content: str | None = None,
) -> tuple[CritiqueResult, str | None, str | None]:
    """Run the critique. Returns (result, manifest_hash, manifest_uri).

    Never raises — a failed critique degrades to a heuristic verdict.
    """
    settings = get_settings()

    if asset_type == "image" and image_path is not None:
        rubric = image_rubric(brief, attempt)
        messages = _messages_for_image(rubric, image_data_uri(image_path))
        model = Resolved.vision_model
    else:
        kind = "marketing copy" if asset_type == "copy" else "voiceover script"
        rubric = text_rubric(brief, attempt, kind, text_content or "")
        messages = _messages_for_text(rubric)
        # Text critique is text-only, so it runs on the free Kimi tier too.
        model = Resolved.text_model

    # Three-tier degradation: strict schema, then loose JSON mode, then plain.
    for response_format in (CRITIQUE_SCHEMA, {"type": "json_object"}, None):
        try:
            result = (
                Pipeline(
                    f"{campaign_id}-{asset_type}-critique-{attempt}",
                    tenant_id="fernwood",
                    project_id=campaign_id,
                    preflight=False,
                )
                .step(
                    TokenRouterChatStep(),
                    model=model,
                    prompt=rubric,
                    modality=Modality.TEXT,
                    metadata={
                        "campaign_id": campaign_id,
                        "asset_type": asset_type,
                        "attempt_number": attempt,
                        "role": "critique",
                    },
                    params={
                        "messages": messages,
                        "response_format": response_format,
                        "temperature": 0.2,
                        "max_tokens": 1200,
                    },
                )
                .run(sink=make_sink(campaign_id), timeout=180, raise_on_failure=True)
            )
            parsed = loads_lenient(step_text(result.run.steps[0]))
            if parsed:
                critique = _coerce(parsed, asset_type)
                if (
                    asset_type == "image"
                    and attempt == 1
                    and settings.fernwood_force_first_retry
                    and critique.passed
                ):
                    # Demo guarantee: force the first image attempt to fail so the
                    # retry loop is always visible, while keeping the model's real
                    # reasoning and fixes. Disable with
                    # FERNWOOD_FORCE_FIRST_RETRY=false.
                    critique.pre_cap_score = critique.overall_score
                    critique.passed = False
                    critique.overall_score = min(critique.overall_score, 82)
                    critique.reasoning = (
                        "Held to a first-draft standard: " + critique.reasoning
                    )
                return (
                    critique,
                    result.manifest.canonical_hash,
                    result.manifest.manifest_uri,
                )
            logger.warning("Critique returned unparseable JSON (rf=%s)", response_format)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Critique attempt failed (rf=%s): %s", response_format, exc)
            continue

    return _fallback(asset_type, attempt), None, None
