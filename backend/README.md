# Fernwood backend

Python sidecar that runs the real campaign pipeline. It exists because Genblaze
is a Python SDK and because the TokenRouter / ElevenLabs / B2 credentials must
never reach the browser.

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
`TOKENROUTER_API_KEY` and `ELEVENLABS_API_KEY`. `.env*` is already gitignored.

Then sanity-check before demoing:

```bash
curl -s localhost:8787/api/health | python3 -m json.tool
```

## Scripts

## Tests

```bash
uv run pytest              # 150 offline tests, no keys, no network (~65s)
uv run pytest -m live      # 11 live tests against real TokenRouter/ElevenLabs/B2
```

Live tests are excluded by default (they cost money). They exist because the
offline suite cannot catch upstream contract drift — the image size floor, the
watermark default, which models return usable JSON, and whether the B2 key still
works have each broken at least once.

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

Per campaign, three sequential tracks (image → audio → copy). Each **attempt**
is its own `Pipeline.run()` with a fresh `ObjectStorageSink`, chained to the
previous attempt via `from_result()` so `parent_run_id` records the retry
lineage. That gives one verifiable manifest per attempt — including the rejected
ones, which is the whole provenance story.

### Storage layout

```
campaigns/{id}/campaign.json                              # our Campaign object
campaigns/{id}/runs/fernwood/{date}/{run_id}/manifest.json # genblaze provenance
campaigns/{id}/runs/fernwood/{date}/{run_id}/assets/...    # image / audio bytes
index/campaigns.json                                       # Library rollup
```

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
