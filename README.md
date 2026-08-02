# Fernwood

AI brand campaign asset generator with a **self-critique and retry pipeline**, built for the
Backblaze Generative AI Media Hackathon.

Give it a brand brief; it generates a campaign key visual, a voiceover, and a marketing copy suite.
Each asset is then **critiqued by a vision model against the brief's own tone and palette**, and
rejected work is automatically regenerated with a prompt informed by that critique — up to three
attempts. Every attempt, including the rejected ones, gets a SHA-256-verified Genblaze provenance
manifest stored in Backblaze B2.

## Stack

| Layer | What runs |
|---|---|
| Orchestration | **Genblaze** (`genblaze-core`) — Pipeline / Step / Manifest / ObjectStorageSink |
| Storage | **Backblaze B2** via `S3StorageBackend.for_backblaze()` |
| Image generation | **TokenRouter** → `bytedance-seed/seedream-4.5`, through a custom `TokenRouterImageProvider` (`SyncProvider`) |
| Brand film | **TokenRouter** → `MiniMax-Hailuo-2.3` image-to-video, through a custom `TokenRouterVideoProvider` (**async `BaseProvider`** — submit / poll / fetch_output) |
| Critique + copy | **TokenRouter** → `openai/gpt-5.4` (vision + strict JSON schema) |
| Voiceover | **TokenRouter** `openai/gpt-audio-mini` → **Deepgram** Aura → **ElevenLabs**, tried in order with automatic fallback (custom `SyncProvider` for each) |
| Frontend | React 19 + Vite + Tailwind v4, live progress over SSE |

Every inference call now goes through a **single TokenRouter key** — image,
video, critique, copy and voiceover. ElevenLabs remains wired as an optional
voiceover backend but is no longer required.

> **Why voiceover has three backends.** ElevenLabs' free tier is 10,000
> characters/month; a handful of campaigns exhaust it, after which every call
> returns `auth_failure` and the audio track dies mid-run — which is exactly
> what happened during development. `FERNWOOD_TTS_PROVIDER=auto` now tries
> TokenRouter, then Deepgram Aura, then ElevenLabs, falling through on **any**
> failure, so no single vendor's quota can cost a campaign its voiceover.
> Pinning an explicit backend disables fallback, so a misconfiguration surfaces
> instead of being silently papered over.

### Two provider styles, chosen by the upstream API

`docs/guides/new-provider.md` says to use `SyncProvider` unless the API requires
polling — and both cases occur here, so both are implemented:

- **Images** are synchronous (`POST /v1/images/generations` returns the URL), so
  `TokenRouterImageProvider` subclasses `SyncProvider` and implements `generate()`.
- **Video** is a genuine task queue (`POST` returns a `task_id`;
  `GET /v1/video/generations/{id}` reports `NOT_START → SUCCESS`), so
  `TokenRouterVideoProvider` subclasses `BaseProvider` and implements the real
  `submit` / `poll` / `fetch_output` lifecycle.

### Embedded provenance

Beyond writing manifests to B2, the delivered MP4 / JPEG / MP3 each carry their
SHA-256 manifest **inside the container** (`genblaze_core.media` handlers). A
downloaded asset can be verified on its own:

```python
from genblaze_core.media import get_handler
manifest = get_handler("video/mp4").extract("brand-film.mp4")
manifest.verify()          # True — full attempt history, no B2 required
```

Deliverables live under `campaigns/{id}/delivery/`, deliberately separate from
the sink's `runs/` tree: embedding rewrites bytes, and the originals are what
the manifest's digests commit to.

## Run it

Two terminals.

```bash
# 1. backend  (Genblaze is a Python SDK, and keys must not reach the browser)
cd backend
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload

# 2. frontend
npm install
npm run dev            # http://localhost:3000
```

Copy `.env.example` → `.env` and fill in `TOKENROUTER_API_KEY` and your B2
credentials. `DEEPGRAM_API_KEY` and `ELEVENLABS_API_KEY` are optional voiceover
fallbacks; Deepgram also powers the audio-verification tests. Then check everything is wired:

```bash
curl -s localhost:8787/api/health | python3 -m json.tool
```

`FERNWOOD_STORAGE=local` runs the identical pipeline against local disk if you want to work without
B2 — same sink, same key layout, same manifests.

> **B2 note:** the S3 API rejects Backblaze *master* keys ("Malformed Access Key Id"). You need a
> non-master application key — its key ID is 25 characters, not the 12-character account ID.

## What one campaign produces

| Asset | How |
|---|---|
| Key visual | Generated, critiqued by a vision model, retried up to 3× |
| Voiceover | Script written by an LLM, spoken by TokenRouter TTS, critiqued |
| Copy suite | Headline, subheadline, body, CTA, 3 bullets, 2 social posts — critiqued |
| Brand film *(opt-in)* | The **approved** key visual animated into a 6s cinematic spot |

The film is deliberately derived from the still that already passed critique, so
it inherits an approved composition and palette instead of inventing a new
scene. Its provenance record says plainly that the motion itself was not
independently scored.

## How the retry loop works

```
for attempt in 1..3:
    Pipeline.run()                       # one run, one manifest, per attempt
    critique  = vision model vs. brief   # tone / palette / craft, scored 0-100
    if critique.passed: stop
    prompt += critique.suggestedFixes    # the causal link
```

Each attempt is its own `Pipeline.run()` chained to the previous via `from_result()`, so
`parent_run_id` records the retry lineage. That is deliberate: a rejected attempt is evidence, and
it needs its own manifest rather than being overwritten.

## Tests

```bash
cd backend
uv run pytest              # 264 offline tests — no keys, no network
uv run pytest -m live      # 62 live tests against the real APIs
```

The live suite drives a complete campaign through the HTTP API exactly as the
browser does, then asserts on what a judge would check: critique scores are real
and varied (not canned), retry prompts carry the prior critique's feedback, the
image decodes, the voiceover **transcribes back to the generated script** (via Deepgram STT, which returns the words and nothing else), and
every manifest downloaded from B2 passes `Manifest.verify()`.

See [backend/README.md](backend/README.md) for architecture, storage layout, and a list of upstream
API behaviours that will bite you.
