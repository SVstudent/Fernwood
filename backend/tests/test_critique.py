"""Critique parsing, coercion, and the degradation ladder.

These guard the failure modes that would silently fake the self-critique
feature: unparseable JSON, models returning 0-1 scores, models returning
passed=true alongside a failing score, and the empty-response case.
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.pipeline.critique import _coerce, _fallback, _messages_for_image
from app.pipeline.schemas import CRITIQUE_SCHEMA, loads_lenient


class TestLoadsLenient:
    def test_plain_json(self):
        assert loads_lenient('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        """anthropic models wrap output in ```json fences."""
        assert loads_lenient('```json\n{"a": 1}\n```') == {"a": 1}

    def test_bare_fence(self):
        assert loads_lenient('```\n{"a": 1}\n```') == {"a": 1}

    def test_json_with_prose_around_it(self):
        assert loads_lenient('Here you go:\n{"a": 1}\nHope that helps!') == {"a": 1}

    def test_nested_braces_recovered(self):
        out = loads_lenient('preamble {"a": {"b": [1,2]}} trailing')
        assert out == {"a": {"b": [1, 2]}}

    @pytest.mark.parametrize("bad", ["", "   ", "not json at all", "[1,2,3]", None])
    def test_unparseable_returns_none(self, bad):
        assert loads_lenient(bad) is None

    def test_empty_string_is_none_not_crash(self):
        """gemini returns HTTP 200 with empty content — must not raise."""
        assert loads_lenient("") is None


class TestCoerce:
    def _payload(self, **over):
        base = {
            "overallScore": 90,
            "passed": True,
            "reasoning": "Good.",
            "suggestedFixes": "None.",
            "criteria": [
                {
                    "name": "Tone Match",
                    "score": 90,
                    "targetScore": 85,
                    "passed": True,
                    "feedback": "ok",
                },
                {
                    "name": "Brand Consistency",
                    "score": 88,
                    "targetScore": 80,
                    "passed": True,
                    "feedback": "ok",
                },
                {
                    "name": "Technical Clarity",
                    "score": 91,
                    "targetScore": 80,
                    "passed": True,
                    "feedback": "ok",
                },
            ],
        }
        base.update(over)
        return base

    def test_happy_path(self):
        r = _coerce(self._payload(), "image")
        assert r.passed is True
        assert r.overall_score == 90
        assert len(r.criteria) == 3

    def test_pass_is_recomputed_not_trusted(self):
        """Models routinely return passed=true with a failing score."""
        r = _coerce(self._payload(overallScore=60, passed=True), "image")
        assert r.passed is False

    def test_pass_recomputed_the_other_way(self):
        r = _coerce(self._payload(overallScore=95, passed=False), "image")
        assert r.passed is True

    def test_threshold_boundary(self):
        t = get_settings().fernwood_pass_threshold
        assert _coerce(self._payload(overallScore=t), "image").passed is True
        assert _coerce(self._payload(overallScore=t - 1), "image").passed is False

    def test_fractional_scores_scaled_to_100(self):
        """Models love returning 0.87 instead of 87."""
        r = _coerce(self._payload(overallScore=0.87), "image")
        assert r.overall_score == 87

    def test_scores_clamped_to_range(self):
        assert _coerce(self._payload(overallScore=250), "image").overall_score == 100
        assert _coerce(self._payload(overallScore=-40), "image").overall_score == 0

    def test_non_numeric_score_falls_back(self):
        r = _coerce(self._payload(overallScore="excellent"), "image")
        assert 0 <= r.overall_score <= 100

    def test_criteria_padded_to_three(self):
        """ProvenanceLog renders a bar per criterion; fewer than 3 looks broken."""
        r = _coerce(self._payload(criteria=[]), "image")
        assert len(r.criteria) == 3
        assert {c.name for c in r.criteria} == {
            "Tone Match",
            "Brand Consistency",
            "Technical Clarity",
        }

    def test_criteria_capped_at_five(self):
        many = [
            {"name": f"C{i}", "score": 80, "targetScore": 80, "passed": True, "feedback": ""}
            for i in range(9)
        ]
        assert len(_coerce(self._payload(criteria=many), "image").criteria) == 5

    def test_malformed_criteria_entries_skipped(self):
        r = _coerce(self._payload(criteria=["garbage", None, 42]), "image")
        assert len(r.criteria) == 3  # padded, not crashed

    def test_missing_text_fields_get_defaults(self):
        r = _coerce({"overallScore": 90, "criteria": []}, "copy")
        assert r.reasoning
        assert r.suggested_fixes


class TestFallback:
    """The demo must never die because a critique response was malformed."""

    def test_attempt_one_fails_attempt_two_passes(self):
        assert _fallback("image", 1).passed is False
        assert _fallback("image", 2).passed is True

    def test_fallback_is_well_formed(self):
        r = _fallback("image", 1)
        assert len(r.criteria) == 3
        assert 0 <= r.overall_score <= 100
        assert "unavailable" in r.reasoning.lower() or "unreachable" in r.reasoning.lower()


class TestVisionMessageShape:
    def test_uses_raw_openai_wire_shape(self):
        """Raw dicts, not genblaze's typed blocks — no extension keys a strict
        gateway could reject."""
        msgs = _messages_for_image("rubric text", "data:image/jpeg;base64,AAAA")
        assert msgs[0]["role"] == "system"
        content = msgs[1]["content"]
        assert content[0] == {"type": "text", "text": "rubric text"}
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        assert content[1]["image_url"]["detail"] == "high"
        assert "media_type" not in content[1]["image_url"]


class TestSchema:
    def test_strict_schema_declares_additional_properties_false(self):
        """OpenAI strict mode rejects a strict schema without this — which is
        why we hand-write the dict instead of passing a Pydantic class."""
        schema = CRITIQUE_SCHEMA["json_schema"]["schema"]
        assert CRITIQUE_SCHEMA["json_schema"]["strict"] is True
        assert schema["additionalProperties"] is False
        assert schema["properties"]["criteria"]["items"]["additionalProperties"] is False

    def test_schema_keys_are_camel_case_for_ts(self):
        props = CRITIQUE_SCHEMA["json_schema"]["schema"]["properties"]
        assert "overallScore" in props
        assert "suggestedFixes" in props
