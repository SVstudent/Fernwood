"""Orchestration for the Campaign Brain — the two phases of a run.

    preflight()  RECALL -> STRATEGY -> FORESIGHT -> AUDIENCE (panel convened)
                 runs BEFORE any generation quota is spent, and returns the
                 strategy the three tracks are aimed with.

    reflect()    AUDIENCE (reaction) -> LEARNING -> persist -> improvement
                 runs AFTER the campaign completes, and is what makes the next
                 run for this brand different from this one.

Split into its own module so app/pipeline/orchestrator.py keeps reading as the
campaign pipeline it was, with the brain as two clearly-bounded calls rather
than fifty interleaved lines.

FAILURE POLICY, applied everywhere in this file: the brain is strictly additive.
Every phase is wrapped, every lobe can independently degrade to 'skipped', and
a total brain outage must leave the campaign byte-for-byte what it would have
been before this feature existed.

Brain progress is reported on the existing `brief_analysis` and `assembly`
stages rather than new PipelineStageId values, deliberately: PipelineRunView
derives its progress bar from the latest log's stage, so inventing stages would
make the bar jump. The live lobe graph rides the separate `brain` SSE event.
"""

from __future__ import annotations

import logging

from app.brain import lobes
from app.brain.metrics import build_run_record, compute_improvement
from app.brain.models import BrainSnapshot, BrainState, CampaignStrategy
from app.brain.store import load_brain, save_brain
from app.config import get_settings
from app.domain.models import Campaign, CampaignBrief
from app.runtime.logbus import Emitter

logger = logging.getLogger(__name__)

_LOBES = ("recall", "strategy", "foresight", "audience", "learning")


class BrainRun:
    """One campaign's use of its brand's brain."""

    def __init__(self, brief: CampaignBrief, campaign_id: str, emit: Emitter) -> None:
        self.brief = brief
        self.campaign_id = campaign_id
        self.emit = emit
        self.brain: BrainState | None = None
        self.snapshot = BrainSnapshot(
            brand_slug="",
            brand_name=brief.brand_name,
            lobes={lobe: "idle" for lobe in _LOBES},
        )
        self.strategy: CampaignStrategy | None = None

    # ------------------------------------------------------------- plumbing
    def _set(self, lobe: str, status: str, manifest: str | None = None) -> None:
        self.snapshot.lobes[lobe] = status
        if manifest:
            self.snapshot.lobe_manifests[lobe] = manifest
        self.emit.brain(self.snapshot)

    # ------------------------------------------------------------ preflight
    def preflight(self) -> CampaignStrategy | None:
        """Recall, strategise, predict and convene the panel. Never raises."""
        settings = get_settings()
        if not settings.fernwood_enable_brain:
            return None

        try:
            return self._preflight()
        except Exception:  # noqa: BLE001 - the campaign must run regardless
            logger.exception("brain preflight failed for %s", self.campaign_id)
            for lobe in _LOBES:
                if self.snapshot.lobes.get(lobe) == "firing":
                    self.snapshot.lobes[lobe] = "skipped"
            return None

    def _preflight(self) -> CampaignStrategy | None:
        from app.config import Resolved

        self.snapshot.model_used = Resolved.text_model

        # --- RECALL -------------------------------------------------------
        self._set("recall", "firing")
        brain = load_brain(self.brief.brand_name)
        self.brain = brain
        laws = lobes.recall(brain)

        self.snapshot.brand_slug = brain.brand_slug
        self.snapshot.brain_version_before = brain.version
        self.snapshot.cold_start = not laws
        self.snapshot.laws_applied = laws
        self.snapshot.improvement = compute_improvement(brain)
        self._set("recall", "done")

        if laws:
            self.emit.info(
                "brief_analysis",
                f"Campaign Brain Recalled {len(laws)} Brand Law(s)",
                f"Loaded brain v{brain.version} for {brain.brand_name} from storage — "
                f"{len(laws)} law(s) learned across {brain.lifetime_campaigns} prior "
                f"campaign(s). Every one cites the rejected attempt that taught it.",
            )
        else:
            self.emit.info(
                "brief_analysis",
                "Campaign Brain Cold Start",
                f"No prior memory for {self.brief.brand_name}. This run becomes the "
                "baseline that future campaigns are measured against.",
            )

        # --- STRATEGY -----------------------------------------------------
        self._set("strategy", "firing")
        strategy, manifest = lobes.strategize(self.brief, laws, self.campaign_id)
        self.strategy = strategy
        self.snapshot.strategy = strategy
        self._set("strategy", "done" if strategy else "skipped", manifest)

        if strategy:
            self.emit.success(
                "brief_analysis",
                "Campaign Strategy Synthesized",
                f'Big idea: "{strategy.big_idea}" — this single directive now aims '
                f"the key visual, the voiceover and the copy suite, with "
                f"{len(strategy.avoid)} anti-pattern(s) drawn from past rejections.",
            )

        # --- FORESIGHT ----------------------------------------------------
        self._set("foresight", "firing")
        foresight, manifest = lobes.foresee(
            self.brief, laws, strategy, self.brain, self.campaign_id
        )
        self.snapshot.foresight = foresight
        self._set("foresight", "done" if foresight else "skipped", manifest)

        if foresight:
            self.emit.info(
                "brief_analysis",
                f"Foresight: Predicting {foresight.predicted_score}/100",
                f"Before spending a single generation call, the brain predicts "
                f"{foresight.predicted_score}/100 across "
                f"{foresight.predicted_retries} retr"
                f"{'y' if foresight.predicted_retries == 1 else 'ies'} "
                f"(confidence {foresight.confidence}%). Expected failure mode: "
                f"{foresight.likely_failure_mode}",
            )

        # --- AUDIENCE (convene the panel; it reacts after the run) ---------
        self._set("audience", "firing")
        personas, manifest = lobes.build_personas(self.brief, brain, self.campaign_id)
        if personas:
            # Persisted immediately so the same panel scores every future
            # campaign for this brand — a resonance trend is meaningless if the
            # judges change between runs.
            brain.personas = personas
            self.snapshot.audience = None
            self._set("audience", "firing", manifest)
            self.emit.info(
                "brief_analysis",
                f"Audience Panel Convened ({len(personas)} personas)",
                "Synthetic reviewers derived from the brief's target audience: "
                + ", ".join(f"{p.name} ({p.age}, {p.occupation})" for p in personas)
                + ". They react to the finished campaign once it is assembled.",
            )
        else:
            self._set("audience", "skipped")

        return strategy

    # -------------------------------------------------------------- reflect
    def reflect(self, campaign: Campaign) -> BrainSnapshot | None:
        """React, learn, persist. Never raises."""
        settings = get_settings()
        if not settings.fernwood_enable_brain or self.brain is None:
            return None

        try:
            return self._reflect(campaign)
        except Exception:  # noqa: BLE001 - the campaign already succeeded
            logger.exception("brain reflection failed for %s", self.campaign_id)
            for lobe in _LOBES:
                if self.snapshot.lobes.get(lobe) == "firing":
                    self.snapshot.lobes[lobe] = "skipped"
            return self.snapshot

    def _reflect(self, campaign: Campaign) -> BrainSnapshot:
        settings = get_settings()
        brain = self.brain
        assert brain is not None  # guarded by reflect()

        # --- FORESIGHT scoring -------------------------------------------
        if self.snapshot.foresight is not None:
            self.snapshot.foresight = lobes.score_foresight(
                self.snapshot.foresight, campaign
            )
            self.emit.info(
                "assembly",
                f"Foresight Calibration: {self.snapshot.foresight.calibration_error} pts off",
                f"Predicted {self.snapshot.foresight.predicted_score}/100, actual "
                f"{campaign.overall_quality_score}/100. The brain scores its own "
                "prediction whether or not the answer flatters it.",
            )

        # --- AUDIENCE reaction -------------------------------------------
        report = None
        if brain.personas:
            self._set("audience", "firing")
            report, manifest = lobes.simulate_audience(
                self.brief, brain.personas, campaign, self.campaign_id
            )
            self.snapshot.audience = report
            self._set("audience", "done" if report else "skipped", manifest)

            if report:
                loudest = min(report.reactions, key=lambda r: r.sentiment)
                self.emit.success(
                    "assembly",
                    f"Audience Resonance: {report.resonance_score}/100",
                    f"{len(report.reactions)} simulated reviewers responded "
                    f"(polarization {report.polarization}). Harshest verdict — "
                    f'{loudest.persona_name}: "{loudest.quote}" '
                    f"Top objection: {report.top_objection}",
                )

        # --- LEARNING -----------------------------------------------------
        self._set("learning", "firing")
        delta, manifest = lobes.learn(
            self.brief, campaign, brain, report, self.campaign_id
        )
        self.snapshot.learning = delta
        self._set("learning", "done" if delta else "skipped", manifest)

        if delta:
            lobes.apply_learning(brain, delta)
            if delta.laws_added or delta.laws_reinforced:
                self.emit.success(
                    "assembly",
                    f"Brain Updated: v{delta.version_before} to v{delta.version_after}",
                    f"{len(delta.laws_added)} new brand law(s) written, "
                    f"{len(delta.laws_reinforced)} reinforced. "
                    + (delta.laws_added[0].text if delta.laws_added else delta.summary),
                )
            else:
                self.emit.info(
                    "assembly",
                    "Brain Reviewed the Run — No New Laws",
                    "Nothing this run met the bar for a durable, evidence-backed "
                    "law. The brain does not pad its memory to look busy.",
                )

        # --- PERSIST + MEASURE -------------------------------------------
        brain.lifetime_campaigns += 1
        brain.history.append(
            build_run_record(
                campaign,
                brain=brain,
                # The version the run was AIMED with, captured before the
                # Learning lobe bumped it moments ago.
                version_at_run=self.snapshot.brain_version_before,
                laws_available=len(self.snapshot.laws_applied),
                resonance_score=report.resonance_score if report else None,
                predicted_score=(
                    self.snapshot.foresight.predicted_score
                    if self.snapshot.foresight
                    else None
                ),
                calibration_error=(
                    self.snapshot.foresight.calibration_error
                    if self.snapshot.foresight
                    else None
                ),
                forced_first_retry=settings.fernwood_force_first_retry,
            )
        )
        save_brain(brain)

        self.snapshot.brain_version_after = brain.version
        # Recomputed AFTER this run is appended, so the panel a judge reads
        # includes the campaign they just watched.
        self.snapshot.improvement = compute_improvement(brain)
        self.emit.brain(self.snapshot)

        improvement = self.snapshot.improvement
        if improvement and improvement.has_baseline:
            self.emit.success(
                "assembly",
                "Measured Self-Improvement",
                improvement.summary,
            )

        return self.snapshot
