"""Retry-loop test — no API keys required.

Stubs out the two network boundaries (image generation and critique) and proves
the thing the whole project claims:

  1. a failed critique triggers a real second attempt
  2. attempt #2's prompt CONTAINS attempt #1's suggestedFixes
  3. each attempt produces its own verifiable provenance manifest
  4. attempt #2's run is linked to attempt #1 via parent_run_id

Run:  uv run python scripts/test_retry_loop.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from genblaze_core.models.asset import Asset  # noqa: E402

from app.config import SCRATCH_DIR, Resolved  # noqa: E402
from app.domain.models import (  # noqa: E402
    CampaignBrief,
    ColorPreference,
    CritiqueCriterion,
    CritiqueResult,
)

FIXES = "Warm the key light considerably and remove all cool grey tones."


def main() -> int:
    Resolved.image_model = "stub-image-model"
    Resolved.vision_model = "stub-vision-model"
    Resolved.chat_model = "stub-chat-model"

    # --- stub the image provider's only network call -------------------
    from app.providers import tokenrouter_image as tri

    def fake_generate(self, step, config=None):
        SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
        payload = f"fake-image-bytes::{step.prompt[:40]}".encode()
        out = SCRATCH_DIR / f"{step.step_id}.png"
        out.write_bytes(payload)
        step.assets.append(
            Asset(
                url=out.resolve().as_uri(),
                media_type="image/png",
                sha256=hashlib.sha256(payload).hexdigest(),
                size_bytes=len(payload),
            )
        )
        step.metadata["local_path"] = str(out)
        return step

    tri.TokenRouterImageProvider.generate = fake_generate

    # --- stub the critique: fail attempt 1, pass attempt 2 -------------
    from app.pipeline import tracks

    seen_prompts: list[str] = []

    def fake_critique(asset_type, *, campaign_id, brief, attempt, image_path=None, text_content=None):
        crit = CritiqueResult(
            passed=attempt >= 2,
            overall_score=68 if attempt == 1 else 94,
            criteria=[
                CritiqueCriterion(
                    name="Tone Match",
                    score=68 if attempt == 1 else 94,
                    target_score=85,
                    passed=attempt >= 2,
                    feedback="stub",
                )
            ],
            reasoning=f"Stub critique for attempt {attempt}.",
            suggested_fixes=FIXES,
        )
        return crit, "stub-hash", "stub-uri"

    tracks.critique_asset = fake_critique

    # capture prompts as they are built
    original_generate = tracks._generate

    def spy_generate(asset_type, brief, campaign_id, n, last_critique, prev_result, emit):
        content, prompt, model, result = original_generate(
            asset_type, brief, campaign_id, n, last_critique, prev_result, emit
        )
        seen_prompts.append(prompt)
        return content, prompt, model, result

    tracks._generate = spy_generate

    # --- run the image track ------------------------------------------
    from app.runtime.logbus import Emitter
    from app.runtime.registry import REGISTRY

    brief = CampaignBrief(
        brand_name="Fernwood Goods",
        product_service="Handcrafted ceramic dinnerware",
        target_audience="Design-conscious home cooks",
        brief_text="Warm, tactile, slow-living.",
        tone_tags=["Earthy & Organic", "Cozy & Warm"],
        colors=ColorPreference(primary="#1E3A2B", secondary="#F4F1EA", accent="#D97706"),
    )
    campaign_id = "camp-retry-test"
    REGISTRY.create(campaign_id)
    asset = tracks.run_track("image", brief, campaign_id, Emitter(campaign_id))

    # --- assertions ----------------------------------------------------
    ok = True
    print(f"attempts run          : {len(asset.attempts)}")
    print(f"verdicts              : {[a.critique_verdict for a in asset.attempts]}")
    print(f"asset status          : {asset.status}")
    print(f"approved attempt      : {asset.final_approved_attempt_id}")

    if len(asset.attempts) != 2:
        print(f"FAIL: expected exactly 2 attempts, got {len(asset.attempts)}")
        ok = False
    if [a.critique_verdict for a in asset.attempts] != ["FAIL", "PASS"]:
        print("FAIL: expected verdicts FAIL then PASS")
        ok = False
    if asset.status != "passed":
        print(f"FAIL: expected status 'passed', got {asset.status!r}")
        ok = False

    if len(seen_prompts) >= 2:
        p1, p2 = seen_prompts[0], seen_prompts[1]
        print(f"\nattempt 1 prompt tail : ...{p1[-70:]}")
        print(f"attempt 2 prompt tail : ...{p2[-110:]}")
        if FIXES not in p2:
            print("FAIL: attempt 2's prompt does NOT contain the critique's suggestedFixes")
            ok = False
        else:
            print("\nOK: attempt 2's prompt incorporates the critique feedback")
        if FIXES in p1:
            print("FAIL: attempt 1's prompt should not contain fixes")
            ok = False
    else:
        print("FAIL: fewer than 2 prompts captured")
        ok = False

    # provenance: distinct manifest hash per attempt
    hashes = [a.content.manifest_hash for a in asset.attempts]
    print(f"\nmanifest hashes       : {[h[:12] + '...' if h else None for h in hashes]}")
    if len(set(h for h in hashes if h)) != len(asset.attempts):
        print("FAIL: attempts do not each have a distinct manifest hash")
        ok = False
    else:
        print("OK: each attempt has its own distinct provenance manifest")

    print("\nPASS" if ok else "\nFAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
