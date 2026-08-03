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

    # Every TEXT-ONLY generation (copy, voiceover script, text critique, and all
    # five Campaign Brain lobes). Blank auto-probes, same as the other two.
    #
    # Kept as its own setting even though it currently resolves to the same
    # model as vision, because the two have genuinely different requirements:
    # this one only needs strict JSON, so it can be pointed at a cheaper or
    # faster model without touching image critique, which needs to see.
    #
    # Benchmarked on a real brain prompt before choosing (scratchpad
    # bench_models.py): gpt-5.4 9.8s honouring the strict schema with no
    # filler; gpt-5.4-mini 5.6s and also clean; claude-sonnet-5 19.9s;
    # gemini-3.5-flash returned unparseable JSON; kimi-k3-free took over two
    # minutes per call and caps at 8 requests/minute, which is unusable for a
    # five-lobe brain. gpt-5.4 wins on accuracy at acceptable latency, and
    # matching the vision model keeps one verified model across the pipeline.
    fernwood_text_model: str = ""

    # Safety net for anyone pointing FERNWOOD_TEXT_MODEL at a free tier. Those
    # carry hard request caps — kimi-k3-free allows 8 per minute and 429s
    # immediately past it, while one campaign makes ~20 text calls. Requests to
    # models named "*-free" are paced client-side; every other model calls
    # straight through with no lock and no overhead. 7 leaves headroom, because
    # the server's window and ours are not clock-synced.
    fernwood_free_tier_rpm: int = 7
    # Retries for a 429 that slipped through the pacing.
    fernwood_rate_limit_retries: int = 3

    # Per-request ceiling for text calls. 120s is generous for the resolved
    # model (~10s observed) and leaves room for a slow gateway without letting
    # a wedged request hold a campaign.
    fernwood_text_request_timeout: float = 120.0

    # --- Video (TokenRouter async task API) ---
    # Verified live: MiniMax-Hailuo-2.3 image-to-video via `first_frame_image`,
    # NOT_START -> SUCCESS in ~115s at 6s/768P.
    fernwood_video_model: str = "MiniMax-Hailuo-2.3"
    fernwood_video_duration: int = 6
    # Shots in the assembled advertisement. Each shot is its own generated
    # frame + its own clip, so this is the main cost/length dial: 3 shots is a
    # complete hook/product/benefit arc, 4 adds a dedicated closing shot.
    # Clamped to 2-4 at the call site.
    fernwood_ad_shots: int = 3
    fernwood_video_size: str = "768P"
    # Master switch; the brief's includeVideo flag still gates it per campaign.
    fernwood_enable_video: bool = True
    # Write the provenance manifest into the delivered mp4/jpg/mp3 containers.
    fernwood_embed_provenance: bool = True

    # --- Voiceover ---
    # "tokenrouter" | "deepgram" | "elevenlabs" | "auto"
    #   auto (default) -> tokenrouter, then deepgram, then elevenlabs; ANY
    #                     failure falls through to the next backend so a vendor
    #                     quota can never cost us the audio track. ElevenLabs is
    #                     last because its free tier is 10k chars/month and
    #                     returns auth_failure once spent.
    fernwood_tts_provider: str = "auto"
    # gpt-audio-mini, not gpt-audio: the latter rejects non-streaming audio
    # output with "Audio output requires stream: true".
    fernwood_tts_model: str = "openai/gpt-audio-mini"
    fernwood_tts_voice: str = "ash"
    fernwood_enable_tts: bool = True

    # --- Deepgram (fallback voiceover backend + STT for verification) ---
    deepgram_api_key: str = ""
    deepgram_tts_model: str = "aura-2-thalia-en"   # Deepgram's "model" IS the voice
    deepgram_stt_model: str = "nova-3"

    # --- ElevenLabs (optional voiceover backend) ---
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"  # provider's own default
    elevenlabs_model: str = "eleven_v3"

    # --- Storage ---
    # "local" -> LocalDiskBackend under backend/var/blobs
    # "b2"    -> S3StorageBackend.for_backblaze(...)
    fernwood_storage: str = "local"
    b2_bucket: str = "fernwood-campaigns"
    b2_region: str = "us-west-004"
    b2_key_id: str = ""
    b2_app_key: str = ""

    # --- Pipeline behaviour ---
    # --- Campaign Brain ---
    # Per-brand persistent memory: recalls laws learned from past rejections,
    # aims the run, predicts its own score, simulates audience reaction, and
    # writes back what it learned. Strictly additive — turning this off returns
    # the pipeline to exactly its pre-brain behaviour.
    fernwood_enable_brain: bool = True

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
    def has_deepgram(self) -> bool:
        return bool(self.deepgram_api_key.strip())

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
    # Text-only workhorse (copy, voiceover script, text critique, Campaign
    # Brain). Separate from chat_model, which must retain vision for image
    # critique.
    text_model: str = ""
    warnings: list[str] = []
