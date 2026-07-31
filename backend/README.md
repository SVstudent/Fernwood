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

| Script | Needs keys? | What it proves |
|---|---|---|
| `uv run python scripts/test_storage.py` | no | Pipeline → ObjectStorageSink → `Manifest.verify() == True`, URL rewritten to `/api/media/...` |
| `uv run python scripts/test_retry_loop.py` | no | A failed critique triggers attempt 2, whose prompt contains attempt 1's `suggestedFixes`; each attempt gets its own manifest |
| `uv run python scripts/probe_tokenrouter.py` | **yes** | Which models the key can reach, the raw `/v1/images/generations` envelope, and whether the vision critique path actually works |

Run `probe_tokenrouter.py` first after adding a key — it validates the two
assumptions most likely to be wrong (image model IDs and the response shape).

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
