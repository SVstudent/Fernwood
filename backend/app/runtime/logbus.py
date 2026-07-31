"""Emitter that turns pipeline progress into PipelineStageLog frames.

Titles and message wording deliberately mirror the original mock in
src/services/pipelineService.ts, because PipelineRunView derives its progress
bar from log.stage and filters the retry feed on
`type === 'warning' && attemptDetails`. Matching the shapes means no component
changes.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime

from app.domain.models import Attempt, AssetType, Campaign, LogType, PipelineStageId, PipelineStageLog
from app.runtime.registry import REGISTRY

_counter = itertools.count()


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class Emitter:
    def __init__(self, campaign_id: str) -> None:
        self.campaign_id = campaign_id

    def _log(
        self,
        stage: PipelineStageId,
        type_: LogType,
        title: str,
        message: str,
        attempt: Attempt | None = None,
        asset_type: AssetType | None = None,
    ) -> None:
        entry = PipelineStageLog(
            id=f"log-{self.campaign_id}-{next(_counter)}",
            stage=stage,
            type=type_,
            title=title,
            message=message,
            timestamp=now_iso(),
            attempt_details=attempt,
            asset_type=asset_type,
        )
        REGISTRY.publish(self.campaign_id, "log", entry.ts())

    def info(self, stage, title, message, asset_type=None) -> None:
        self._log(stage, "info", title, message, None, asset_type)

    def success(self, stage, title, message, attempt=None, asset_type=None) -> None:
        self._log(stage, "success", title, message, attempt, asset_type)

    def warning(self, stage, title, message, attempt=None, asset_type=None) -> None:
        self._log(stage, "warning", title, message, attempt, asset_type)

    def error(self, stage, title, message, asset_type=None) -> None:
        self._log(stage, "error", title, message, None, asset_type)

    def campaign(self, campaign: Campaign) -> None:
        REGISTRY.publish(self.campaign_id, "campaign", campaign.ts())

    def done(self, campaign: Campaign) -> None:
        REGISTRY.publish(
            self.campaign_id, "done", {"status": campaign.status, "campaign": campaign.ts()}
        )

    def fatal(self, stage: str, message: str) -> None:
        REGISTRY.publish(self.campaign_id, "error", {"stage": stage, "message": message})
