"""Domain models, prompts, and colour naming."""

from __future__ import annotations

import pytest

from app.domain.models import (
    Asset,
    Attempt,
    AttemptContent,
    Campaign,
    CampaignAssets,
    ColorPreference,
    CritiqueCriterion,
    CritiqueResult,
)
from app.domain.prompts import (
    build_copy_prompt,
    build_image_prompt,
    build_voiceover_prompt,
    hex_to_name,
)


class TestHexToName:
    """Image models cannot read hex; these names are what steer the render."""

    @pytest.mark.parametrize(
        "hex_code,expected_substring",
        [
            ("#1E3A2B", "green"),
            ("#F4F1EA", "white"),
            ("#D97706", "orange"),
            ("#2563EB", "blue"),
            ("#E11D48", "crimson"),
            ("#000000", "black"),
            ("#FFFFFF", "white"),
        ],
    )
    def test_recognisable_names(self, hex_code, expected_substring):
        assert expected_substring in hex_to_name(hex_code).lower()

    def test_dark_colours_get_deep_qualifier(self):
        assert hex_to_name("#1E3A2B").startswith("deep")

    def test_greys_have_no_hue(self):
        assert "grey" in hex_to_name("#808080") or "grey" in hex_to_name("#7A7A7A")

    def test_shorthand_hex(self):
        assert hex_to_name("#0F0") == hex_to_name("#00FF00")

    def test_accepts_missing_hash(self):
        assert hex_to_name("1E3A2B") == hex_to_name("#1E3A2B")

    def test_malformed_input_returns_original(self):
        assert hex_to_name("not-a-colour") == "not-a-colour"


class TestPrompts:
    def test_image_prompt_includes_brand_and_colour_words(self, brief):
        p = build_image_prompt(brief, 1, None)
        assert "Fernwood Goods" in p
        assert "forest green" in p  # translated, not raw hex
        assert "#1E3A2B" in p  # hex retained for precision
        assert "Earthy & Organic" in p

    def test_first_attempt_has_no_revision_block(self, brief):
        assert "REVISION" not in build_image_prompt(brief, 1, None)

    @pytest.mark.parametrize(
        "builder", [build_image_prompt, build_copy_prompt, build_voiceover_prompt]
    )
    def test_retry_prompt_carries_critique_fixes(self, brief, builder):
        """The core claim of the project: attempt N+1 is informed by attempt N."""
        critique = CritiqueResult(
            passed=False,
            overall_score=68,
            criteria=[],
            reasoning="Too cold and grey.",
            suggested_fixes="Warm the key light and remove cool greys.",
        )
        p = builder(brief, 2, critique)
        assert "Warm the key light and remove cool greys." in p
        assert "REVISION 2" in p
        assert "68" in p

    def test_image_prompt_forbids_text_in_render(self, brief):
        assert "No text" in build_image_prompt(brief, 1, None)


class TestWireSerialization:
    """The backend must emit exactly what src/types.ts declares."""

    def _attempt(self) -> Attempt:
        return Attempt(
            id="att-1",
            attempt_number=1,
            provider_name="TokenRouter Image",
            model_name="seedream",
            prompt_used="p",
            timestamp="2026-08-01T00:00:00Z",
            critique_verdict="FAIL",
            critique=CritiqueResult(
                passed=False,
                overall_score=70,
                criteria=[
                    CritiqueCriterion(
                        name="Tone Match",
                        score=70,
                        target_score=85,
                        passed=False,
                        feedback="f",
                    )
                ],
                reasoning="r",
                suggested_fixes="s",
            ),
            content=AttemptContent(image_url="/api/media/x.png"),
        )

    def test_keys_are_camel_case(self):
        d = self._attempt().ts()
        assert "attemptNumber" in d and "attempt_number" not in d
        assert "critiqueVerdict" in d
        assert d["critique"]["overallScore"] == 70
        assert d["critique"]["criteria"][0]["targetScore"] == 85

    def test_unset_optional_fields_are_omitted_not_null(self):
        """AttemptContent has ~15 optionals; TS expects absent, not null."""
        d = self._attempt().ts()["content"]
        assert d["imageUrl"] == "/api/media/x.png"
        assert "audioScript" not in d
        assert "headline" not in d

    def test_final_approved_attempt_id_null_survives(self):
        """`string | null` in TS — null means 'nothing passed' and is meaningful,
        so it must not be stripped by exclude_none."""
        asset = Asset(id="a", campaign_id="c", type="image", attempts=[], status="failed")
        d = asset.ts()
        assert "finalApprovedAttemptId" in d
        assert d["finalApprovedAttemptId"] is None

    def test_campaign_assets_serialize_as_nested_object(self):
        asset = Asset(
            id="a",
            campaign_id="c",
            type="image",
            attempts=[self._attempt()],
            final_approved_attempt_id="att-1",
            status="passed",
        )
        campaign = Campaign(
            id="c",
            brand_name="B",
            product_service="P",
            target_audience="T",
            colors=ColorPreference(primary="#1", secondary="#2", accent="#3"),
            created_at="t",
            updated_at="t",
            assets=CampaignAssets(image=asset),
        )
        d = campaign.ts()
        assert set(d["assets"]) == {"image"}
        assert d["assets"]["image"]["finalApprovedAttemptId"] == "att-1"
        assert d["overallQualityScore"] == 0

    def test_brief_accepts_camel_case_input(self):
        """The frontend posts camelCase; pydantic must accept it by alias."""
        from app.domain.models import CampaignBrief

        b = CampaignBrief.model_validate(
            {
                "brandName": "X",
                "productService": "Y",
                "targetAudience": "Z",
                "briefText": "t",
                "toneTags": ["a"],
                "colors": {"primary": "#1", "secondary": "#2", "accent": "#3"},
            }
        )
        assert b.brand_name == "X"
        assert b.tone_tags == ["a"]
