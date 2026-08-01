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
| Image generation | **TokenRouter** → `bytedance-seed/seedream-4.5`, through a custom `TokenRouterImageProvider` |
| Critique + copy | **TokenRouter** → `openai/gpt-5.4` (vision + strict JSON schema) |
| Voiceover | **ElevenLabs** via Genblaze's native `ElevenLabsTTSProvider` |
| Frontend | React 19 + Vite + Tailwind v4, live progress over SSE |

All inference goes through TokenRouter; ElevenLabs handles audio only.

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

Copy `.env.example` → `.env` and fill in `TOKENROUTER_API_KEY`, `ELEVENLABS_API_KEY`, and your B2
credentials. Then check everything is wired:

```bash
curl -s localhost:8787/api/health | python3 -m json.tool
```

`FERNWOOD_STORAGE=local` runs the identical pipeline against local disk if you want to work without
B2 — same sink, same key layout, same manifests.

> **B2 note:** the S3 API rejects Backblaze *master* keys ("Malformed Access Key Id"). You need a
> non-master application key — its key ID is 25 characters, not the 12-character account ID.

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
uv run pytest              # 190 offline tests — no keys, no network
uv run pytest -m live      # 46 live tests against the real APIs
```

The live suite drives a complete campaign through the HTTP API exactly as the
browser does, then asserts on what a judge would check: critique scores are real
and varied (not canned), retry prompts carry the prior critique's feedback, the
image decodes, the voiceover **transcribes back to the generated script**, and
every manifest downloaded from B2 passes `Manifest.verify()`.

See [backend/README.md](backend/README.md) for architecture, storage layout, and a list of upstream
API behaviours that will bite you.
