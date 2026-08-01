"""Campaign-level status semantics.

'failed' must mean "an asset could not be produced", not "an asset didn't clear
the critique threshold" — otherwise a run that delivered all three assets gets
misreported as a failure.
"""

from __future__ import annotations

import hashlib

import pytest
from genblaze_core.exceptions import ProviderError
from genblaze_core.models.asset import Asset as GbAsset
from genblaze_core.models.enums import ProviderErrorCode

from app.config import SCRATCH_DIR, Resolved
from app.domain.models import CritiqueCriterion, CritiqueResult
from app.pipeline import tracks
from app.pipeline.orchestrator import draft_campaign, run_campaign
from app.runtime.registry import REGISTRY


@pytest.fixture(autouse=True)
def stub_env(monkeypatch):
    Resolved.image_model = "stub"
    Resolved.vision_model = "stub"
    Resolved.chat_model = "stub"
    monkeypatch.setenv("FERNWOOD_ENABLE_TTS", "false")


def _emit_file_asset(step, payload: bytes, media_type: str, text: str | None = None):
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    out = SCRATCH_DIR / f"{step.step_id}.bin"
    out.write_bytes(payload)
    step.assets.append(
        GbAsset(
            url=out.resolve().as_uri(),
            media_type=media_type,
            sha256=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
            metadata={"text": text} if text else {},
        )
    )
    step.metadata["local_path"] = str(out)
    return step


@pytest.fixture
def stub_generation(monkeypatch):
    def img(self, step, config=None):
        return _emit_file_asset(step, b"img", "image/png")

    COPY = (
        '{"headline":"H","subheadline":"S","bodyText":"B","callToAction":"C",'
        '"keyBenefitBullets":["a","b","c"],"socialPosts":["p","q"],'
        '"script":"Words.","voiceDescription":"Warm"}'
    )

    def chat(self, step, config=None):
        return _emit_file_asset(step, COPY.encode(), "application/json", COPY)

    monkeypatch.setattr(
        "app.providers.tokenrouter_image.TokenRouterImageProvider.generate", img
    )
    monkeypatch.setattr(
        "app.providers.tokenrouter_chat.TokenRouterChatStep.generate", chat
    )


def _stub_critique(monkeypatch, passed: bool):
    def fake(asset_type, *, campaign_id, brief, attempt, image_path=None, text_content=None):
        return (
            CritiqueResult(
                passed=passed,
                overall_score=90 if passed else 60,
                criteria=[
                    CritiqueCriterion(
                        name="Tone Match",
                        score=90 if passed else 60,
                        target_score=85,
                        passed=passed,
                        feedback="f",
                    )
                ],
                reasoning="r",
                suggested_fixes="fix it",
            ),
            "h",
            "u",
        )

    monkeypatch.setattr(tracks, "critique_asset", fake)


def _run(brief, cid):
    REGISTRY.create(cid)
    return run_campaign(draft_campaign(cid, brief), brief)


class TestCampaignStatus:
    def test_all_assets_pass_completes(self, brief, stub_generation, monkeypatch):
        _stub_critique(monkeypatch, True)
        c = _run(brief, "camp-ok")
        assert c.status == "completed"
        assert c.overall_quality_score >= 85

    def test_assets_produced_but_never_pass_still_completes(
        self, brief, stub_generation, monkeypatch
    ):
        """The kit exists; the per-asset status carries the quality verdict."""
        _stub_critique(monkeypatch, False)
        c = _run(brief, "camp-lowquality")
        assert c.status == "completed"
        assert c.assets.image.status == "failed"
        assert c.assets.image.attempts  # but the work is there
        assert c.overall_quality_score > 0

    def test_provider_outage_marks_campaign_failed(self, brief, monkeypatch):
        """Nothing could be produced — that is a genuine failure."""

        def dead(self, step, config=None):
            raise ProviderError("down", error_code=ProviderErrorCode.SERVER_ERROR)

        monkeypatch.setattr(
            "app.providers.tokenrouter_image.TokenRouterImageProvider.generate", dead
        )
        monkeypatch.setattr(
            "app.providers.tokenrouter_chat.TokenRouterChatStep.generate", dead
        )
        _stub_critique(monkeypatch, True)
        c = _run(brief, "camp-outage")
        assert c.status == "failed"
        assert c.assets.image.attempts == []

    def test_counts_reflect_retries(self, brief, stub_generation, monkeypatch):
        _stub_critique(monkeypatch, False)
        c = _run(brief, "camp-counts")
        # 3 asset types x 3 attempts each = 9, with 2 retries per type
        assert c.total_attempts_count == 9
        assert c.retry_count == 6

    def test_terminal_done_event_emitted(self, brief, stub_generation, monkeypatch):
        _stub_critique(monkeypatch, True)
        _run(brief, "camp-done")
        names = [e.name for e in REGISTRY.get("camp-done").events]
        assert names[-1] == "done"
        assert "campaign" in names

    def test_campaign_persisted_for_library(self, brief, stub_generation, monkeypatch):
        from app.storage import index

        _stub_critique(monkeypatch, True)
        _run(brief, "camp-persist")
        stored = index.get_campaign("camp-persist")
        assert stored["status"] == "completed"
        assert set(stored["assets"]) == {"image", "audio", "copy"}
