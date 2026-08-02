# Fernwood backend

Python sidecar that runs the real campaign pipeline. It exists because Genblaze
is a Python SDK and because the TokenRouter / Deepgram / ElevenLabs / B2
credentials must never reach the browser.

## Run

Two terminals.

```bash
# 1. backend  (port 8787 — :8000 is often taken by other local services)
cd backend
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload

# 2. frontend
npm install
npm run dev            # http://localhost:3000, proxies /api -> :8787
```

**Single worker only.** The run registry and its SSE fan-out are in-process, so
`--workers > 1` would let a browser connect to a worker that has never heard of
its run.

## Configure

Copy `.env.example` to `.env` at the **project root** and fill in
`TOKENROUTER_API_KEY` plus your B2 credentials. `DEEPGRAM_API_KEY` and
`ELEVENLABS_API_KEY` are optional voiceover fallbacks. `.env*` is already
gitignored.

Then sanity-check before demoing:

```bash
curl -s localhost:8787/api/health | python3 -m json.tool
```

## Tests

```bash
uv run pytest              # 264 offline tests — no keys, no network
uv run pytest -m live      # 62 live tests against real TokenRouter/Deepgram/B2 (~4min)
```

Live tests are excluded by default (they cost money). They exist because the
offline suite cannot catch upstream contract drift — the image size floor, the
watermark default, which models return usable JSON, and whether the B2 key still
works have each broken at least once.

Three live files matter most:

| File | What it proves |
|---|---|
| `test_live_demo_path.py` | 26 assertions over **one real campaign** driven through the HTTP API exactly as the browser does: varied non-canned critique scores, retry prompts carrying prior feedback, decodable image, Range-served MP3, and manifests downloaded from B2 that pass `Manifest.verify()` |
| `test_live_audio_content.py` | The voiceover **actually says the script** — transcribed with Deepgram STT and compared word-for-word (100% overlap, 1.000 confidence observed). Plus duration, speaking rate, and a size-vs-duration check that catches truncation |
| `test_live_integration.py` | Per-service contracts: model availability, the image size floor, and that the vision model returns non-empty structured JSON |

`test_live_demo_path.py` deletes its campaign afterwards so runs don't pollute
the demo library. Set `FERNWOOD_KEEP_TEST_CAMPAIGNS=1` to keep it.

### Why transcription rather than "is it a valid MP3"

A well-formed MP3 can be silence, a truncated buffer, or the wrong take. Audible
playback could not be confirmed in an automated browser — media elements never
load there, and a synthesized WAV control stalls identically — so the audio is
verified by transcribing it and diffing against the generated script instead.

## Scripts

| Script | Needs keys? | What it proves |
|---|---|---|
| `uv run python scripts/test_storage.py` | no | Pipeline → ObjectStorageSink → `Manifest.verify() == True`, URL rewritten to `/api/media/...` |
| `uv run python scripts/test_retry_loop.py` | no | A failed critique triggers attempt 2, whose prompt contains attempt 1's `suggestedFixes`; each attempt gets its own manifest |
| `uv run python scripts/probe_tokenrouter.py` | **yes** | Which models the key can reach, the raw `/v1/images/generations` envelope, and whether the vision critique path actually works |

Run `probe_tokenrouter.py` first after changing keys or models.

## Upstream facts learned the hard way

Each of these was discovered by probing the live API, and each would silently
break the product:

- **Image size floor.** Seedream rejects anything under **3,686,400 px**
  (`1024x1024` → HTTP 400). The default `2560x1440` is exactly that floor and
  16:9.
- **Watermark.** Seedream stamps a visible "AI generated" badge by default. The
  vision critique caught it and capped Technical Clarity at ~72/80. We send
  `watermark: false` (a real upstream bool — passing a string returns a Go
  unmarshal error naming the field).
- **`google/gemini-3.5-flash` returns HTTP 200 with EMPTY content** on
  multimodal requests, and never clean JSON. This is the dangerous one: it looks
  healthy while silently degrading every critique to the heuristic fallback.
  Startup now probes for *non-empty parseable JSON*, not just a 200.
- **`anthropic/*` rejects `temperature`** ("deprecated for this model" → 400)
  and ignores `json_schema`, inventing its own keys.
- **`openai/gpt-5.4` is the only model tested that does vision *and* obeys the
  strict schema**, so it serves both critique and copy.
- **Hex colours mean nothing to an image model.** Passing `#1E3A2B` produced
  images that failed palette adherence every time; `hex_to_name()` converts it
  to "deep forest green", which is what actually steers the render.
- **B2 master keys do not work with the S3 API** ("Malformed Access Key Id").
  The S3 endpoint needs a non-master application key — a 25-char key ID, not the
  12-char account ID.

## Architecture

```
POST /api/campaigns            -> starts a run in a worker thread, returns 202
GET  /api/campaigns/{id}/stream-> SSE: log / campaign / done / error frames
GET  /api/campaigns            -> Library listing from storage
GET  /api/media/{key}          -> serves local bytes, or 307s to a presigned B2 URL
GET  /api/health               -> key + model + storage status
```

Per campaign, three sequential tracks (image → audio → copy), plus an opt-in
brand-film track. Each **attempt**
is its own `Pipeline.run()` with a fresh `ObjectStorageSink`, chained to the
previous attempt via `from_result()` so `parent_run_id` records the retry
lineage. That gives one verifiable manifest per attempt — including the rejected
ones, which is the whole provenance story.

### Storage layout

```
campaigns/{id}/campaign.json                               # our Campaign object
campaigns/{id}/runs/fernwood/{date}/{run_id}/manifest.json # genblaze provenance
campaigns/{id}/runs/fernwood/{date}/{run_id}/assets/...    # image / audio / video bytes
campaigns/{id}/delivery/{image,audio,video}.{ext}          # same assets, manifest EMBEDDED
index/campaigns.json                                       # Library rollup
```

`delivery/` is intentionally a separate tree. Embedding rewrites the container
bytes, and the sink-stored originals are exactly what the manifest's SHA-256
digests commit to — overwriting them in place would invalidate the hash being
embedded.

### Voiceover: three backends, tried in order

`FERNWOOD_TTS_PROVIDER=auto` runs **TokenRouter → Deepgram → ElevenLabs**,
falling through on any failure.

| Backend | Route | Notes |
|---|---|---|
| `tokenrouter` | `POST /v1/chat/completions` with `modalities:["text","audio"]` | `openai/gpt-audio-mini`. There is **no** `/v1/audio/speech` — `tts-1` and `gpt-4o-mini-tts` return 503 model_not_found. `openai/gpt-audio` (non-mini) rejects non-streaming audio with "requires stream: true". |
| `deepgram` | `POST /v1/speak?model=<voice>&encoding=mp3` | Aura. The `model` **is** the voice (`aura-2-thalia-en`). Returns `audio/mpeg` bytes directly. |
| `elevenlabs` | genblaze's native `ElevenLabsTTSProvider` | Last resort: free tier is 10k chars/month and returns `auth_failure` once spent. |

Naming a backend explicitly disables fallback, so a misconfiguration fails
loudly instead of being silently substituted.

`app/providers/deepgram_tts.py` also exposes `transcribe()` (Deepgram STT,
nova-3). The audio-verification tests use it because a purpose-built ASR returns
the spoken words and nothing else — an audio *chat* model prepends commentary
("Here it is, verbatim:") and mis-hears proper nouns, which made those tests
flaky. Observed confidence: 1.000, 100% word overlap.

### Brand film (opt-in, `includeVideo: true`)

`TokenRouterVideoProvider` is the project's only **async** provider, because
TokenRouter's video API is a real task queue. It subclasses `BaseProvider`:

| Method | Does |
|---|---|
| `submit()` | POSTs the task, returns `SubmitResult(prediction_id, estimated_seconds=110)` so the runner backs off sensibly |
| `poll()` | `True` on any TERMINAL state — success *or* failure, per the base contract |
| `fetch_output()` | Raises on failure; otherwise downloads the mp4, hashes it, attaches the `Asset` |

Image-to-video needs a **publicly fetchable** first frame, so the approved key
visual is handed over as a presigned B2 URL. That means video requires
`FERNWOOD_STORAGE=b2` — a `LocalDiskBackend` URL points at localhost and
TokenRouter's upstream cannot reach it. The track logs a clear warning and skips
rather than failing the campaign.

Providers disagree on the first-frame field name; `image_field_for()` maps it
(`first_frame_image` for Hailuo, `image` for Kling, `input_reference` for
Happyhorse, `images` array for Seedance).

Switching `FERNWOOD_STORAGE=local` → `b2` swaps `LocalDiskBackend` for
`S3StorageBackend.for_backblaze()` in `app/storage/factory.py` and changes
nothing else — the same `ObjectStorageSink` and key layout are used either way.

## Gotchas worth knowing

- **Provider scratch files must live under the system temp dir.**
  `ObjectStorageSink` reads `file://` assets through `_read_local_file()`, which
  allows only `{tempfile.gettempdir(), /tmp}`, and exposes no way to widen it.
  This is why `ElevenLabsTTSProvider` is constructed with **no** `output_dir`.
- **Never emit `text:` scheme assets.** The llm-calls doc's `ChatStep` recipe
  does, but `AssetTransfer` treats only `file` as local, so a `text:` URL falls
  through to the HTTP branch and fails `write_run()` — which also skips the
  manifest upload. Chat output is written as a temp `.json` file instead.
- **`Pipeline(preflight=False)`** everywhere: preflight validates model slugs
  against a `ModelRegistry`, and our TokenRouter slugs are in none.
- **`key_strategy` must be passed explicitly** — the `ObjectStorageSink` default
  is `CONTENT_ADDRESSABLE`, not `HIERARCHICAL`.
