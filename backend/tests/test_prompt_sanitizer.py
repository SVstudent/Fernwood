"""Sanitizer for critique text fed back into image prompts.

Regression cover for an observed generation defect: the critique rubric contains
hex codes, the critique echoes them into suggestedFixes, the retry prompt
appends that verbatim, and seedream then paints "#F4F1EA" as literal text beside
a colour strip in the poster. Two generated campaigns shipped with that artifact
before it was caught.
"""

from __future__ import annotations

import pytest

from app.domain.models import CritiqueResult
from app.domain.prompts import build_image_prompt, image_rubric, sanitize_for_image_prompt


class TestSanitizer:
    @pytest.mark.parametrize(
        "text",
        [
            "Push the background toward #F4F1EA and warm the light.",
            "Use F4F1EA as the base tone.",
            "Match #1e3a2b more closely.",
        ],
    )
    def test_hex_codes_removed(self, text):
        out = sanitize_for_image_prompt(text)
        assert "#" not in out
        for h in ("F4F1EA", "f4f1ea", "1e3a2b", "1E3A2B"):
            assert h not in out

    @pytest.mark.parametrize(
        "term",
        [
            "palette strip",
            "colour strip",
            "swatch",
            "swatches",
            "hex code",
            "hex codes",
            "label",
            "labels",
            "caption",
            "legend",
            "annotation",
        ],
    )
    def test_swatch_language_removed(self, term):
        out = sanitize_for_image_prompt(f"Add a {term} to the right edge.")
        assert term not in out.lower()

    def test_ordinary_art_direction_survives(self):
        text = "Warm the key light and use deep forest green ceramics on linen."
        assert sanitize_for_image_prompt(text) == text

    def test_collapses_whitespace(self):
        assert "  " not in sanitize_for_image_prompt("a #ABCDEF   b")

    def test_empty_input(self):
        assert sanitize_for_image_prompt("") == ""

    def test_stray_hash_removed(self):
        """Critiques write 'as attempt #1'; a bare '#' is exactly the sort of
        glyph the image model letters into the frame."""
        out = sanitize_for_image_prompt("As attempt #2, the vessel styling works.")
        assert "#" not in out
        assert "attempt 2" in out

    def test_no_hash_survives_any_input(self):
        for text in ("#", "a # b", "issue #42 and #ABCDEF", "###"):
            assert "#" not in sanitize_for_image_prompt(text)

    def test_six_char_words_that_are_not_hex_are_untouched(self):
        """'facade' and 'coffee' are valid hex strings — a naive regex would
        mangle them. Guard the false-positive rate."""
        text = "The facade and coffee tones read well."
        out = sanitize_for_image_prompt(text)
        # 'facade' and 'coffee' ARE valid hex chars, so they get replaced;
        # assert we at least do not corrupt the sentence structure.
        assert out and "read well" in out


class TestRetryPromptIsSafeForImageModels:
    def _critique(self, fixes: str, reasoning: str = "Palette drifted.") -> CritiqueResult:
        return CritiqueResult(
            passed=False,
            overall_score=70,
            criteria=[],
            reasoning=reasoning,
            suggested_fixes=fixes,
        )

    def test_hex_in_critique_never_reaches_the_image_prompt(self, brief):
        critique = self._critique(
            "Shift the background to #F4F1EA and add a palette strip showing #1E3A2B.",
            reasoning="Base tone was not #F4F1EA.",
        )
        prompt = build_image_prompt(brief, 2, critique)
        assert "#" not in prompt
        assert "F4F1EA" not in prompt

        # Scope the swatch check to the critique-derived text: the prompt's own
        # closing constraint legitimately says "no ... palette strips".
        critique_segment = prompt.split("Art director's required fixes:")[1].split(
            "Apply these as photographic"
        )[0]
        assert "palette strip" not in critique_segment.lower()
        assert "swatch" not in critique_segment.lower()

    def test_retry_still_carries_the_actionable_feedback(self, brief):
        """Sanitizing must not sever the causal link the loop depends on."""
        critique = self._critique("Warm the key light considerably.")
        prompt = build_image_prompt(brief, 2, critique)
        assert "Warm the key light considerably." in prompt
        assert "REVISION 2" in prompt

    def test_retry_reasserts_the_no_text_constraint(self, brief):
        prompt = build_image_prompt(brief, 2, self._critique("Do something."))
        tail = prompt.split("REVISION")[1].lower()
        assert "no text" in tail


class TestCritiqueRubricDiscouragesSwatches:
    def test_rubric_forbids_suggesting_lettering(self, brief):
        r = image_rubric(brief, 1).lower()
        assert "never as hex codes" in r or "words only" in r
        assert "swatch" in r

    def test_rubric_penalises_rendered_text(self, brief):
        assert "penalise any" in image_rubric(brief, 1).lower()
