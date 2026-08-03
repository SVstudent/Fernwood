"""Structured-output schemas for the five brain lobes.

Hand-written dicts for the same reason app/pipeline/schemas.py uses them:
genblaze's coerce_response_format() forces {"strict": True} on Pydantic models,
but pydantic never emits "additionalProperties": false — and strict mode rejects
a schema without it.

STRICT-MODE RULE that bites here repeatedly: every key in `properties` must also
appear in `required`. There is no such thing as an optional field in a strict
schema; model an absent value as an empty string or empty array instead.
"""

from __future__ import annotations

from typing import Any


def _schema(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {"name": name, "strict": True, "schema": schema},
    }


STRATEGY_SCHEMA = _schema(
    "CampaignStrategy",
    {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "bigIdea",
            "positioning",
            "visualDirection",
            "voiceDirection",
            "copyAngle",
            "avoid",
        ],
        "properties": {
            "bigIdea": {"type": "string"},
            "positioning": {"type": "string"},
            "visualDirection": {"type": "string"},
            "voiceDirection": {"type": "string"},
            "copyAngle": {"type": "string"},
            "avoid": {
                "type": "array",
                "minItems": 2,
                "maxItems": 6,
                "items": {"type": "string"},
            },
        },
    },
)


FORESIGHT_SCHEMA = _schema(
    "Foresight",
    {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "predictedScore",
            "predictedRetries",
            "likelyFailureMode",
            "confidence",
            "rationale",
        ],
        "properties": {
            "predictedScore": {"type": "integer", "minimum": 0, "maximum": 100},
            "predictedRetries": {"type": "integer", "minimum": 0, "maximum": 6},
            "likelyFailureMode": {"type": "string"},
            "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
            "rationale": {"type": "string"},
        },
    },
)


PERSONAS_SCHEMA = _schema(
    "AudiencePanel",
    {
        "type": "object",
        "additionalProperties": False,
        "required": ["personas"],
        "properties": {
            "personas": {
                "type": "array",
                "minItems": 4,
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "name",
                        "age",
                        "occupation",
                        "location",
                        "mindset",
                        "skepticism",
                        "mediaDiet",
                    ],
                    "properties": {
                        "name": {"type": "string"},
                        "age": {"type": "integer", "minimum": 13, "maximum": 95},
                        "occupation": {"type": "string"},
                        "location": {"type": "string"},
                        "mindset": {"type": "string"},
                        "skepticism": {"type": "integer", "minimum": 0, "maximum": 100},
                        "mediaDiet": {"type": "string"},
                    },
                },
            }
        },
    },
)


REACTIONS_SCHEMA = _schema(
    "AudienceReactions",
    {
        "type": "object",
        "additionalProperties": False,
        "required": ["reactions", "consensus", "topObjection"],
        "properties": {
            "consensus": {"type": "string"},
            "topObjection": {"type": "string"},
            "reactions": {
                "type": "array",
                "minItems": 1,
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "personaName",
                        "sentiment",
                        "verdict",
                        "quote",
                        "objection",
                        "wouldAct",
                        "attentionSeconds",
                    ],
                    "properties": {
                        "personaName": {"type": "string"},
                        "sentiment": {"type": "integer", "minimum": 0, "maximum": 100},
                        "verdict": {
                            "type": "string",
                            "enum": ["loves", "likes", "indifferent", "dislikes"],
                        },
                        "quote": {"type": "string"},
                        "objection": {"type": "string"},
                        "wouldAct": {"type": "integer", "minimum": 0, "maximum": 100},
                        "attentionSeconds": {"type": "number", "minimum": 0, "maximum": 60},
                    },
                },
            },
        },
    },
)


LEARNING_SCHEMA = _schema(
    "LearningDelta",
    {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "newLaws", "reinforcedLawIds"],
        "properties": {
            "summary": {"type": "string"},
            "reinforcedLawIds": {
                "type": "array",
                "maxItems": 10,
                "items": {"type": "string"},
            },
            "newLaws": {
                "type": "array",
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text", "category", "confidence", "evidence"],
                    "properties": {
                        "text": {"type": "string"},
                        "category": {
                            "type": "string",
                            "enum": ["visual", "voice", "copy", "audience", "strategy"],
                        },
                        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                        "evidence": {"type": "string"},
                    },
                },
            },
        },
    },
)
