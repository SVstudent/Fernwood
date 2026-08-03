# Fernwood

AI brand campaign asset generator with a **self-critique and retry pipeline** and a **persistent,
per-brand Campaign Brain**, built for the Backblaze Generative AI Media Hackathon.

Give it a brand brief; it generates a campaign key visual, a voiceover, and a marketing copy suite.
Each asset is then **critiqued by a vision model against the brief's own tone and palette**, and
rejected work is automatically regenerated with a prompt informed by that critique — up to three
attempts. Every attempt, including the rejected ones, gets a SHA-256-verified Genblaze provenance
manifest stored in Backblaze B2.

Then the **Campaign Brain** reads that archive back, and the next campaign for the same brand
starts knowing what the last one got wrong.

## The Campaign Brain

Fernwood already stored every rejected attempt alongside the structured critique that rejected it.
That archive was write-only: campaign #7 for a brand began from the same blank slate as campaign
#1 and re-made the same mistakes. The Brain turns the storage layer into memory.

Five lobes, each a real inference call, each producing its own provenance manifest:

| Lobe | What it does |
|---|---|
| **Recall** | Loads this brand's accumulated laws from `brains/{slug}/brain.json` in B2. A storage read, not an inference call — memory you have to re-derive isn't memory. |
| **Strategy** | Turns brief + laws into one campaign strategy. The image, voiceover and copy generators never see each other's output, so this is the only thing making them one campaign. |
| **Foresight** | Predicts the score and the likely failure mode **before any generation quota is spent**, then gets scored against the real outcome. |
| **Audience** | Convenes 4 synthetic personas from the brief's target audience and has them react to the finished work — with the sentence each would actually say. |
| **Learning** | Distils durable brand laws from this run's rejections and audience objections, and writes them back. Version bumped, snapshot preserved. |

### Every law is a citation, not an opinion

A `BrandLaw` carries the campaign, the attempt and the critique text that produced it. Laws that
arrive without evidence are **discarded before they are saved** — the value of the store is that
you can click from any rule back to the rejected asset that proves it. A law rediscovered by a
later campaign is `reinforced`, which raises its rank when laws compete for prompt budget.

### Measured self-improvement

Every run appends a `RunRecord` to the brain's history, and the improvement panel compares the
brand's first recorded run against its most recent one:

```
RUN 1 (brain v0, 0 laws)          RUN 3 (brain v2, 7 laws)
first-attempt avg   68     →      86        ▲ +18
retries              4     →       1        ▼ −3
audience resonance  61     →      74        ▲ +13
```

The headline metric is **first-attempt quality**, not final quality: the retry loop drags almost
everything over the line eventually, so what memory should change is how good the opening shot is
before any critique fires.

Three deliberate constraints keep that number honest:

- **One run is a baseline, not a trend.** With a single record the panel says so and claims nothing.
- **`FERNWOOD_FORCE_FIRST_RETRY` is compensated for.** That flag caps the first image critique to
  guarantee a visible retry; the real score is preserved as `preCapScore` and the metric reads that
  instead. Scoring the brain against a number the demo harness chose would measure the harness.
- **Mismatched conditions are disclosed.** Runs made under different settings are flagged with a
  caveat rather than silently compared.

### Running the cold-vs-warm demo

```bash
curl -X DELETE localhost:8787/api/brain/{brand-slug}   # true cold start
# run the brief → baseline recorded
# run the same brief again → the panel measures the difference
```

The reset deletes only the live brain; the versioned `v{n}.json` snapshots survive, because they
are the evidence behind past improvement claims.

### The Brain never fails a campaign

Every lobe is independently wrapped and degrades to `skipped`. Strategy is optional at every call
site, so `FERNWOOD_ENABLE_BRAIN=false` — or a total brain outage — returns the pipeline to
byte-for-byte its pre-brain behaviour. The pipeline is the product; the brain is the multiplier.

## Stack

| Layer | What runs |
|---|---|
| Orchestration | **Genblaze** (`genblaze-core`) — Pipeline / Step / Manifest / ObjectStorageSink |
| Storage | **Backblaze B2** via `S3StorageBackend.for_backblaze()` |
| Image generation | **TokenRouter** → `bytedance-seed/seedream-4.5`, through a custom `TokenRouterImageProvider` (`SyncProvider`) |
| Brand film | **TokenRouter** → `MiniMax-Hailuo-2.3` image-to-video, through a custom `TokenRouterVideoProvider` (**async `BaseProvider`** — submit / poll / fetch_output) |
| Critique, copy, scripts, **Campaign Brain** | **TokenRouter** → `openai/gpt-5.4` (vision + strict JSON schema) |
| Voiceover | **TokenRouter** `openai/gpt-audio-mini` → **Deepgram** Aura → **ElevenLabs**, tried in order with automatic fallback (custom `SyncProvider` for each) |
| Frontend | React 19 + Vite + Tailwind v4, live progress over SSE |

Every inference call now goes through a **single TokenRouter key** — image,
video, critique, copy, voiceover and the Campaign Brain. ElevenLabs remains
wired as an optional voiceover backend but is no longer required.

> **How the text model was chosen.** Text-only work — copy, voiceover scripts,
> text critique and all five brain lobes — resolves through its own
> `FERNWOOD_TEXT_MODEL` setting, separate from vision, because it only needs
> strict JSON rather than sight. Candidates were benchmarked on a real Campaign
> Brain prompt rather than picked by price or reputation:
>
> | Model | Latency | Result |
> |---|---|---|
> | `openai/gpt-5.4` | **9.8s** | strict schema honoured, no filler — **chosen** |
> | `openai/gpt-5.4-mini` | 5.6s | also clean; the faster fallback |
> | `anthropic/claude-sonnet-5` | 19.9s | correct but slowest; rejects `temperature` |
> | `google/gemini-3.5-flash` | 12.1s | unparseable JSON |
> | `moonshotai/kimi-k3-free` | **>120s** | plus an 8-request/minute cap — unusable for a five-lobe brain |
>
> A free tier was trialled and rejected on measurement. What survived it is
> `app/providers/ratelimit.py`, which paces any model named `*-free` under its
> request cap and is inert for everything else — so pinning a free model
> degrades speed rather than silently losing every lobe to 429s.

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
| **Advertisement** *(opt-in)* | A **cut, multi-shot commercial** — see below |

## The advertisement track

The earlier version of this animated the one approved key visual: a slow push-in
on a still. Technically a video, creatively a motion test. An advertisement has
structure, so this track builds one:

```
STORYBOARD   an LLM writes 3-4 shots against the campaign's own strategy,
             approved copy and recorded voiceover — hook, product, benefit, close
    ↓
FRAMES       each shot gets its OWN generated first frame: a different scene,
             not a re-crop of the key visual
    ↓
CLIPS        each frame is animated with that shot's own camera move
             (push-in, parallax drift, rack focus, slow tilt)
    ↓
CUT          shots concatenated, the approved voiceover laid across the whole
             film, closing on a branded end card
```

**Shots render concurrently.** The video API is a genuine task queue
(submit/poll/fetch, ~2 minutes per clip), so three sequential shots would be six
minutes of mostly waiting. Concurrency is what makes a four-shot ad viable live.

**The narration is split, not rewritten.** The voiceover has already been
generated, critiqued and transcription-verified against its script; the
storyboard divides those exact words across the shots so picture and voice are
cut together.

**The only lettering is ours.** Every shot prompt forbids text in frame, because
generated lettering comes out malformed. The brand name, headline and CTA are
drawn onto the end card with Pillow — correct spelling, correct brand colours,
contrast picked by luminance so a pale brand doesn't go white-on-white.

ffmpeg ships bundled via `imageio-ffmpeg`, so cloning this repo does not require
`brew install ffmpeg`.

### Degradation is stepwise

Each stage produces something usable alone, so nothing is all-or-nothing:

| Failure | Result |
|---|---|
| Storyboard model unreachable | A structural fallback shot list — still multi-shot, generic wording |
| One shot fails | The ad is cut from the shots that rendered; the gap is shown in the UI |
| ffmpeg missing | The longest single clip ships as the film |
| Voiceover missing | The cut ships silent |

The provenance record states plainly that the generated **motion** was not
scored by any model — only the shot list, the palette lineage and the structural
completeness of the cut were checked. Overstating what was verified is worse
than a modest claim.

> **One ffmpeg trap worth knowing.** Muxing the voiceover the obvious way hangs.
> `-shortest` alone truncates the *picture* to the length of the narration,
> silently deleting the end card. Adding `apad` fixes that but pads
> **infinitely** — combined with `-shortest` and a filtergraph output, ffmpeg
> never sees an end-of-stream and runs until killed. The fix is to bound the
> output with an explicit `-t` of the video's own duration.

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
uv run pytest              # 303 offline tests — no keys, no network
uv run pytest -m live      # 62 live tests against the real APIs
```

The live suite drives a complete campaign through the HTTP API exactly as the
browser does, then asserts on what a judge would check: critique scores are real
and varied (not canned), retry prompts carry the prior critique's feedback, the
image decodes, the voiceover **transcribes back to the generated script** (via Deepgram STT, which returns the words and nothing else), and
every manifest downloaded from B2 passes `Manifest.verify()`.

See [backend/README.md](backend/README.md) for architecture, storage layout, and a list of upstream
API behaviours that will bite you.
