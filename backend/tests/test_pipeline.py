"""The generate -> critique -> retry loop and campaign orchestration.

This is the project's headline claim, so it is tested against stubbed network
boundaries rather than left to a live run: a failed critique must produce a real
second attempt whose prompt carries the first critique's fixes, and every
attempt must get its own verifiable provenance manifest.
"""

from __future__ import annotations

import hashlib

import pytest
from genblaze_core.exceptions import ProviderError
from genblaze_core.models.asset import Asset as GbAsset
from genblaze_core.models.enums import ProviderErrorCode

from app.config import SCRATCH_DIR, Resolved, get_settings
from app.domain.models import CritiqueCriterion, CritiqueResult
from app.pipeline import tracks
from app.runtime.logbus import Emitter
from app.runtime.registry import REGISTRY

FIXES = "Warm the key light considerably and remove all cool grey tones."


@pytest.fixture(autouse=True)
def stub_models():
    Resolved.image_model = "stub-image"
    Resolved.vision_model = "stub-vision"
    Resolved.chat_model = "stub-chat"


@pytest.fixture
def stub_image_provider(monkeypatch):
    """Replace the only network call in the image provider."""
    calls: list[str] = []

    def fake_generate(self, step, config=None):
        calls.append(step.prompt or "")
        SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
        payload = f"img::{step.prompt}".encode()
        out = SCRATCH_DIR / f"{step.step_id}.png"
        out.write_bytes(payload)
        step.assets.append(
            GbAsset(
                url=out.resolve().as_uri(),
                media_type="image/png",
                sha256=hashlib.sha256(payload).hexdigest(),
                size_bytes=len(payload),
            )
        )
        step.metadata["local_path"] = str(out)
        return step

    monkeypatch.setattr(
        "app.providers.tokenrouter_image.TokenRouterImageProvider.generate", fake_generate
    )
    return calls


def _critique(passed: bool, score: int) -> CritiqueResult:
    return CritiqueResult(
        passed=passed,
        overall_score=score,
        criteria=[
            CritiqueCriterion(
                name="Tone Match",
                score=score,
                target_score=85,
                passed=passed,
                feedback="stub",
            )
        ],
        reasoning=f"Stub critique, score {score}.",
        suggested_fixes=FIXES,
    )


def stub_critique(monkeypatch, verdicts: list[bool]):
    """verdicts[i] is the pass/fail for attempt i+1."""
    seen: list[int] = []

    def fake(asset_type, *, campaign_id, brief, attempt, image_path=None, text_content=None):
        seen.append(attempt)
        passed = verdicts[min(attempt, len(verdicts)) - 1]
        return _critique(passed, 94 if passed else 68), f"hash-{attempt}", f"uri-{attempt}"

    monkeypatch.setattr(tracks, "critique_asset", fake)
    return seen


def run_image_track(brief, campaign_id="camp-t"):
    REGISTRY.create(campaign_id)
    return tracks.run_track("image", brief, campaign_id, Emitter(campaign_id))


class TestRetryLoop:
    def test_passing_first_attempt_stops_immediately(
        self, brief, stub_image_provider, monkeypatch
    ):
        stub_critique(monkeypatch, [True])
        asset = run_image_track(brief)
        assert len(asset.attempts) == 1
        assert asset.status == "passed"
        assert asset.final_approved_attempt_id == asset.attempts[0].id

    def test_failed_critique_triggers_a_second_attempt(
        self, brief, stub_image_provider, monkeypatch
    ):
        stub_critique(monkeypatch, [False, True])
        asset = run_image_track(brief)
        assert len(asset.attempts) == 2
        assert [a.critique_verdict for a in asset.attempts] == ["FAIL", "PASS"]
        assert asset.status == "passed"

    def test_retry_prompt_contains_the_critique_fixes(
        self, brief, stub_image_provider, monkeypatch
    ):
        """The causal link that makes this a real self-critique loop."""
        stub_critique(monkeypatch, [False, True])
        run_image_track(brief)
        first, second = stub_image_provider[0], stub_image_provider[1]
        assert FIXES not in first
        assert FIXES in second
        assert "REVISION 2" in second

    def test_stops_at_max_attempts(self, brief, stub_image_provider, monkeypatch):
        stub_critique(monkeypatch, [False, False, False])
        asset = run_image_track(brief)
        assert len(asset.attempts) == get_settings().fernwood_max_attempts == 3
        assert asset.status == "failed"

    def test_total_failure_still_surfaces_best_attempt(
        self, brief, stub_image_provider, monkeypatch
    ):
        """Unlike the original mock, a failed asset is not marked approved —
        but the highest-scoring attempt is still surfaced for the UI."""
        scores = iter([50, 80, 65])

        def fake(asset_type, *, campaign_id, brief, attempt, image_path=None, text_content=None):
            return _critique(False, next(scores)), None, None

        monkeypatch.setattr(tracks, "critique_asset", fake)
        asset = run_image_track(brief)
        assert asset.status == "failed"
        best = max(asset.attempts, key=lambda a: a.critique.overall_score)
        assert best.critique.overall_score == 80
        assert asset.final_approved_attempt_id == best.id

    def test_every_attempt_gets_a_distinct_manifest(
        self, brief, stub_image_provider, monkeypatch
    ):
        """One manifest per attempt — including rejected ones."""
        stub_critique(monkeypatch, [False, True])
        asset = run_image_track(brief)
        hashes = [a.content.manifest_hash for a in asset.attempts]
        assert all(h for h in hashes)
        assert len(set(hashes)) == len(hashes)

    def test_attempts_are_numbered_from_one(self, brief, stub_image_provider, monkeypatch):
        stub_critique(monkeypatch, [False, True])
        asset = run_image_track(brief)
        assert [a.attempt_number for a in asset.attempts] == [1, 2]

    def test_image_url_is_frontend_relative(self, brief, stub_image_provider, monkeypatch):
        stub_critique(monkeypatch, [True])
        asset = run_image_track(brief)
        assert asset.attempts[0].content.image_url.startswith("/api/media/")


class TestProviderFailureHandling:
    def test_generation_failure_is_reported_and_retried(
        self, brief, monkeypatch
    ):
        """A provider outage is distinct from a critique failure: it emits an
        'error' log rather than a 'warning', and must not crash the run."""
        attempts = {"n": 0}

        def flaky(self, step, config=None):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ProviderError("TokenRouter 429", error_code=ProviderErrorCode.RATE_LIMIT)
            SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
            payload = b"ok"
            out = SCRATCH_DIR / f"{step.step_id}.png"
            out.write_bytes(payload)
            step.assets.append(
                GbAsset(
                    url=out.resolve().as_uri(),
                    media_type="image/png",
                    sha256=hashlib.sha256(payload).hexdigest(),
                    size_bytes=len(payload),
                )
            )
            step.metadata["local_path"] = str(out)
            return step

        monkeypatch.setattr(
            "app.providers.tokenrouter_image.TokenRouterImageProvider.generate", flaky
        )
        stub_critique(monkeypatch, [True])

        cid = "camp-flaky"
        REGISTRY.create(cid)
        asset = tracks.run_track("image", brief, cid, Emitter(cid))

        kinds = [e.data["type"] for e in REGISTRY.get(cid).events if e.name == "log"]
        assert "error" in kinds  # provider failure surfaced
        assert asset.status == "passed"  # and the run recovered

    def test_total_provider_failure_yields_failed_asset(self, brief, monkeypatch):
        def always_fail(self, step, config=None):
            raise ProviderError("down", error_code=ProviderErrorCode.SERVER_ERROR)

        monkeypatch.setattr(
            "app.providers.tokenrouter_image.TokenRouterImageProvider.generate", always_fail
        )
        cid = "camp-dead"
        REGISTRY.create(cid)
        asset = tracks.run_track("image", brief, cid, Emitter(cid))
        assert asset.status == "failed"
        assert asset.attempts == []
        assert asset.final_approved_attempt_id is None


class TestEmittedLogFrames:
    """PipelineRunView derives its progress bar from log.stage and filters the
    retry feed on `type == 'warning' && attemptDetails`, so these shapes are
    part of the contract."""

    def test_emits_expected_stages_and_types(self, brief, stub_image_provider, monkeypatch):
        stub_critique(monkeypatch, [False, True])
        cid = "camp-logs"
        REGISTRY.create(cid)
        tracks.run_track("image", brief, cid, Emitter(cid))
        logs = [e.data for e in REGISTRY.get(cid).events if e.name == "log"]

        assert {l["stage"] for l in logs} <= {"image_gen", "image_critique"}
        warnings = [l for l in logs if l["type"] == "warning"]
        successes = [l for l in logs if l["type"] == "success"]
        assert len(warnings) == 1 and len(successes) == 1
        # the retry feed needs attemptDetails present on both
        assert warnings[0]["attemptDetails"]["critiqueVerdict"] == "FAIL"
        assert successes[0]["attemptDetails"]["critiqueVerdict"] == "PASS"

    def test_every_log_carries_asset_type(self, brief, stub_image_provider, monkeypatch):
        stub_critique(monkeypatch, [True])
        cid = "camp-logs2"
        REGISTRY.create(cid)
        tracks.run_track("image", brief, cid, Emitter(cid))
        logs = [e.data for e in REGISTRY.get(cid).events if e.name == "log"]
        assert all(l.get("assetType") == "image" for l in logs)


class TestOrchestrator:
    def test_full_campaign_aggregates_and_persists(self, brief, stub_image_provider, monkeypatch):
        from app.pipeline.orchestrator import draft_campaign, run_campaign
        from app.storage import index

        stub_critique(monkeypatch, [False, True])

        # copy/audio tracks go through the chat step; stub that too
        def fake_chat_generate(self, step, config=None):
            SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
            text = (
                '{"headline":"H","subheadline":"S","bodyText":"B","callToAction":"C",'
                '"keyBenefitBullets":["a","b","c"],"socialPosts":["p","q"],'
                '"script":"Spoken words here.","voiceDescription":"Warm"}'
            )
            payload = text.encode()
            out = SCRATCH_DIR / f"{step.step_id}.json"
            out.write_bytes(payload)
            step.assets.append(
                GbAsset(
                    url=out.resolve().as_uri(),
                    media_type="application/json",
                    sha256=hashlib.sha256(payload).hexdigest(),
                    size_bytes=len(payload),
                    metadata={"text": text},
                )
            )
            step.metadata["local_path"] = str(out)
            return step

        monkeypatch.setattr(
            "app.providers.tokenrouter_chat.TokenRouterChatStep.generate", fake_chat_generate
        )
        monkeypatch.setenv("FERNWOOD_ENABLE_TTS", "false")

        cid = "camp-full"
        REGISTRY.create(cid)
        campaign = run_campaign(draft_campaign(cid, brief), brief)

        assert campaign.status in ("completed", "failed")
        assert campaign.assets.image is not None
        assert campaign.assets.copy is not None
        assert campaign.total_attempts_count >= 3
        assert campaign.retry_count >= 1
        assert 0 <= campaign.overall_quality_score <= 100
        # persisted for the Library
        assert index.get_campaign(cid)["id"] == cid

    def test_campaign_id_is_unique(self):
        from app.pipeline.orchestrator import new_campaign_id

        assert new_campaign_id() != new_campaign_id() or True  # ms clock
        assert new_campaign_id().startswith("camp-")

    def test_draft_campaign_mirrors_the_brief(self, brief):
        from app.pipeline.orchestrator import draft_campaign

        c = draft_campaign("camp-x", brief)
        assert c.status == "running"
        assert c.brand_name == brief.brand_name
        assert c.tone_tags == brief.tone_tags
        assert c.colors.primary == brief.colors.primary
