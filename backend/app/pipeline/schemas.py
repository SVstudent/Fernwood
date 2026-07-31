"""Structured-output schemas + lenient parsing.

JUDGMENT CALL: response_format is a hand-written dict, NOT a Pydantic class.
genblaze's coerce_response_format() hardcodes {"strict": True} when handed a
Pydantic model, but pydantic's model_json_schema() does not emit
"additionalProperties": false — and OpenAI-strict mode rejects a strict schema
without it. A hand-built dict sidesteps that entirely.

Keys are camelCase so the parsed dict drops straight into the TS CritiqueResult
shape with no remapping.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def _schema(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {"name": name, "strict": True, "schema": schema},
    }


CRITIQUE_SCHEMA = _schema(
    "CritiqueResult",
    {
        "type": "object",
        "additionalProperties": False,
        "required": ["overallScore", "passed", "reasoning", "suggestedFixes", "criteria"],
        "properties": {
            "overallScore": {"type": "integer", "minimum": 0, "maximum": 100},
            "passed": {"type": "boolean"},
            "reasoning": {"type": "string"},
            "suggestedFixes": {"type": "string"},
            "criteria": {
                "type": "array",
                "minItems": 3,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "score", "targetScore", "passed", "feedback"],
                    "properties": {
                        "name": {"type": "string"},
                        "score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "targetScore": {"type": "integer", "minimum": 0, "maximum": 100},
                        "passed": {"type": "boolean"},
                        "feedback": {"type": "string"},
                    },
                },
            },
        },
    },
)


COPY_SCHEMA = _schema(
    "MarketingCopy",
    {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "headline",
            "subheadline",
            "bodyText",
            "callToAction",
            "keyBenefitBullets",
            "socialPosts",
        ],
        "properties": {
            "headline": {"type": "string"},
            "subheadline": {"type": "string"},
            "bodyText": {"type": "string"},
            "callToAction": {"type": "string"},
            "keyBenefitBullets": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {"type": "string"},
            },
            "socialPosts": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "items": {"type": "string"},
            },
        },
    },
)


VOICEOVER_SCHEMA = _schema(
    "Voiceover",
    {
        "type": "object",
        "additionalProperties": False,
        "required": ["script", "voiceDescription"],
        "properties": {
            "script": {"type": "string"},
            "voiceDescription": {"type": "string"},
        },
    },
)


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def loads_lenient(text: str) -> dict[str, Any] | None:
    """Best-effort JSON extraction from an LLM response. None if hopeless."""
    if not text or not text.strip():
        return None

    candidates = [text]
    fenced = _FENCE.search(text)
    if fenced:
        candidates.append(fenced.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate.strip())
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    logger.warning("Could not parse JSON from model output: %.200s", text)
    return None
