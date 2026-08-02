"""Settings singleton. Reads the project-root .env so there is exactly one
place to put keys (root .gitignore already covers `.env*` at any depth)."""

from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

# All provider scratch output MUST live under the system temp dir. genblaze's
# storage/transfer.py reads file:// assets via _read_local_file(), which
# enforces ALLOWED_FILE_ROOTS = {tempfile.gettempdir(), "/tmp"} — and
# ObjectStorageSink constructs its AssetTransfer WITHOUT an allowed_roots
# argument (verified in sink.py:408), so there is no way to widen it.
# Writing provider output anywhere else fails the upload with StorageError.
SCRATCH_DIR = Path(tempfile.gettempdir()) / "fernwood"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- TokenRouter (all image + LLM inference) ---
    tokenrouter_api_key: str = ""
    tokenrouter_base_url: str = "https://api.tokenrouter.com/v1"

    # Leave blank to auto-probe GET /v1/models at startup. Set to hard-override
    # the probe — this is the live-demo panic button.
    fernwood_image_model: str = ""
    fernwood_vision_model: str = ""

    # --- Video (TokenRouter async task API) ---
    # Verified live: MiniMax-Hailuo-2.3 image-to-video via `first_frame_image`,
    # NOT_START -> SUCCESS in ~115s at 6s/768P.
    fernwood_video_model: str = "MiniMax-Hailuo-2.3"
    fernwood_video_duration: int = 6
    fernwood_video_size: str = "768P"
    # Master switch; the brief's includeVideo flag still gates it per campaign.
    fernwood_enable_video: bool = True
    # Write the provenance manifest into the delivered mp4/jpg/mp3 containers.
    fernwood_embed_provenance: bool = True

    # --- ElevenLabs (audio only) ---
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"  # provider's own default
    elevenlabs_model: str = "eleven_v3"
    fernwood_enable_tts: bool = True

    # --- Storage ---
    # "local" -> LocalDiskBackend under backend/var/blobs
    # "b2"    -> S3StorageBackend.for_backblaze(...)
    fernwood_storage: str = "local"
    b2_bucket: str = "fernwood-campaigns"
    b2_region: str = "us-west-004"
    b2_key_id: str = ""
    b2_app_key: str = ""

    # --- Pipeline behaviour ---
    fernwood_max_attempts: int = 3
    fernwood_pass_threshold: int = 85
    # The retry loop is the product story. If every asset passes on attempt 1
    # the demo has no content, so this hard-fails the FIRST image critique
    # while keeping the model's real reasoning/suggestedFixes text.
    fernwood_force_first_retry: bool = True

    # Port 8787, not 8000: :8000 is commonly occupied by other local services.
    # Only used to build LocalDiskBackend durable URLs, which public_media_url()
    # immediately rewrites to relative /api/media/... paths — so stored
    # campaign.json files survive a port change.
    public_api_base: str = "http://127.0.0.1:8787"

    @property
    def local_root(self) -> Path:
        return BACKEND_DIR / "var" / "blobs"

    @property
    def has_tokenrouter(self) -> bool:
        return bool(self.tokenrouter_api_key.strip())

    @property
    def has_elevenlabs(self) -> bool:
        return bool(self.elevenlabs_api_key.strip())

    @property
    def has_b2(self) -> bool:
        return bool(self.b2_key_id.strip() and self.b2_app_key.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Resolved at startup by providers.client.probe_models(); read by the pipeline.
class Resolved:
    image_model: str = ""
    vision_model: str = ""
    chat_model: str = ""
    warnings: list[str] = []
