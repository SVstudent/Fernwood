"""Wire models — camelCase mirrors of src/types.ts.

The frontend types are the contract; these must serialize to exactly what
src/types.ts declares so no .tsx file has to change. Always dump with
`by_alias=True, exclude_none=True` — AttemptContent has ~15 optional fields and
the TS type expects them absent, not null.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

AssetType = Literal["image", "audio", "copy"]
PipelineStageId = Literal[
    "brief_analysis",
    "image_gen",
    "image_critique",
    "audio_gen",
    "audio_critique",
    "copy_gen",
    "copy_critique",
    "assembly",
    "b2_upload",
]
LogType = Literal["info", "success", "warning", "error", "attempt"]


class TSModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    def ts(self) -> dict[str, Any]:
        """Serialize to the exact shape src/types.ts expects."""
        return self.model_dump(by_alias=True, exclude_none=True)


class ColorPreference(TSModel):
    primary: str
    secondary: str
    accent: str


class CampaignBrief(TSModel):
    brand_name: str
    product_service: str
    target_audience: str
    brief_text: str = ""
    tone_tags: list[str] = []
    colors: ColorPreference


class CritiqueCriterion(TSModel):
    name: str
    score: int
    target_score: int
    passed: bool
    feedback: str


class CritiqueResult(TSModel):
    passed: bool
    overall_score: int
    criteria: list[CritiqueCriterion] = []
    reasoning: str
    suggested_fixes: str


class AttemptContent(TSModel):
    # image
    image_url: str | None = None
    svg_data: str | None = None
    aspect_ratio: str | None = None
    # audio
    audio_script: str | None = None
    audio_voice: str | None = None
    duration_seconds: float | None = None
    audio_waveform_data: list[int] | None = None
    audio_url: str | None = None  # additive: real ElevenLabs mp3
    # copy
    headline: str | None = None
    subheadline: str | None = None
    body_text: str | None = None
    call_to_action: str | None = None
    social_posts: list[str] | None = None
    key_benefit_bullets: list[str] | None = None
    # palette
    primary_color: str | None = None
    secondary_color: str | None = None
    accent_color: str | None = None
    # additive provenance fields (rendered by ProvenanceLog if wired)
    manifest_hash: str | None = None
    manifest_uri: str | None = None


class Attempt(TSModel):
    id: str
    attempt_number: int
    provider_name: str
    model_name: str
    prompt_used: str
    timestamp: str
    critique_verdict: Literal["PASS", "FAIL"]
    critique: CritiqueResult
    content: AttemptContent


class Asset(TSModel):
    id: str
    campaign_id: str
    type: AssetType
    attempts: list[Attempt] = []
    final_approved_attempt_id: str | None = None
    status: Literal["pending", "in_progress", "passed", "failed"] = "pending"

    def ts(self) -> dict[str, Any]:
        # finalApprovedAttemptId is `string | null` in TS — null is meaningful
        # (means "nothing passed"), so it must survive exclude_none.
        d = self.model_dump(by_alias=True, exclude_none=True)
        d["finalApprovedAttemptId"] = self.final_approved_attempt_id
        return d


class CampaignAssets(TSModel):
    image: Asset | None = None
    audio: Asset | None = None
    copy: Asset | None = None


class Campaign(TSModel):
    id: str
    brand_name: str
    product_service: str
    target_audience: str
    brief_text: str = ""
    tone_tags: list[str] = []
    colors: ColorPreference
    created_at: str
    updated_at: str
    status: Literal["draft", "running", "completed", "failed"] = "draft"
    assets: CampaignAssets = CampaignAssets()
    overall_quality_score: int = 0
    total_attempts_count: int = 0
    retry_count: int = 0

    def ts(self) -> dict[str, Any]:
        d = self.model_dump(by_alias=True, exclude_none=True)
        d["assets"] = {
            k: getattr(self.assets, k).ts()
            for k in ("image", "audio", "copy")
            if getattr(self.assets, k) is not None
        }
        return d


class PipelineStageLog(TSModel):
    id: str
    stage: PipelineStageId
    type: LogType
    title: str
    message: str
    timestamp: str
    attempt_details: Attempt | None = None
    asset_type: AssetType | None = None
