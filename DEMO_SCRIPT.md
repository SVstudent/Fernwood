# Fernwood — Demo Video Script

**Target runtime: 2:57** (requirement is under 3:00)
Backblaze Generative AI Media Hackathon submission.

---

## BEFORE YOU RECORD

**Environment**
- [ ] Backend up: `cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload`
- [ ] Frontend up: `npm run dev` → `localhost:3000`
- [ ] Sanity check: `curl -s localhost:8787/api/health` shows `"warnings": []` and `"mode": "b2"`
- [ ] Library shows **"Fernwood E2E 1785665186"** as the first card (has the full ad + brain)

**Recording setup**
- [ ] Browser window **1440×900**, zoom **100%**
- [ ] Hide bookmarks bar (`⌘⇧B`)
- [ ] Close other tabs except the two below
- [ ] **Second tab: your Backblaze B2 web console**, with `campaigns/` expanded
      (used in Shot 5 — the single most persuasive Backblaze visual you can show)

**B-roll to capture first**
- [ ] Start a new campaign (**New Brief** → tick *"Also produce a full advertisement"*)
- [ ] Screen-record the pipeline run view for ~90 seconds
- [ ] You'll speed this to **8×** for Shot 2

**Optional but worth it**
Re-run the same brief a second time before recording. The *Measured self-improvement*
panel then shows real deltas (+points, −retries) instead of "baseline recorded."
Add 15s after Shot 6 if you do — and cut Shot 8 to compensate.

---

# THE SCRIPT

## SHOT 1 — Hook · 0:00–0:14

**NAVIGATE:** Start on `localhost:3000` (Library). Don't click anything — slow-scroll
the campaign grid for ~2 seconds, then scroll back to top.

**FRAME:** Full window. Make sure the header's right-hand badges — **`⚡ Genblaze AI`**
and **`🗄 B2 Storage`** — are visible. They're on screen the entire video; establish them now.

> "Every AI campaign tool generates assets. None of them learn. Run the same brand ten
> times, you get the same mistakes ten times. Fernwood is the first one with a memory —
> and that memory is Backblaze."

---

## SHOT 2 — The pipeline · 0:14–0:32   🏷️ GENBLAZE

**NAVIGATE:** Cut to your pre-recorded pipeline B-roll at **8× speed**.

**FRAME:** The dark **Campaign Brain cortex panel** at the top of the run view — lobes
pulsing amber→green with signal dots travelling the edges. Then pan down to the
streaming console log.

> "Give it a brief. Five brain lobes fire before a single image is generated, then image,
> voiceover and copy — each critiqued and retried. **Every one of those is a Genblaze
> Pipeline step.** One run per attempt, which means one signed manifest per attempt —
> including the ones that get rejected."

---

## SHOT 3 — The honest badge · 0:32–0:50

**NAVIGATE:** `Library` → click the first card, **"Fernwood E2E 1785665186"**
(top-left of the grid).

**FRAME:** Land on the result view. **Zoom to the top-left of the hero card** — the amber
pill reading `CRITIQUE: 3/4 PASSED` and the grey chip beside it,
*"image below the 85-point bar — best attempt delivered."*
Then pan right to `QUALITY SCORE 85/100`.

> "It says three of four passed. The key visual scored 81 against an 85 bar — so we ship
> the best attempt and say so. Most demos tell you everything worked. This one shows you
> its own rejects, because every rejected attempt was kept."

---

## SHOT 4 — Where the rejects live · 0:50–1:05   🏷️ BACKBLAZE + GENBLAZE

**NAVIGATE:** Scroll **all the way down** the result page to the **Provenance Log**
section (bottom, headed *"Key Visual Asset Provenance"*). Expand one **FAIL** attempt.

**FRAME:** Zoom on a failed attempt row — its red FAIL verdict, its score, and its
**SHA-256 manifest hash**.

> "Here's attempt one — rejected, 77 out of 100, with the critique that killed it.
> **Genblaze gave it its own manifest, and Backblaze kept it.** Most pipelines overwrite
> failures. This one treats them as evidence."

---

## SHOT 5 — The Brain · 1:05–1:32   🏷️ BACKBLAZE ⭐ THE BIG ONE

**NAVIGATE:** Scroll back to top → click the violet **`Campaign Brain · 49 resonance`**
button (top-right, immediately left of *Tweak Brief & Re-run*).

**FRAME:** Let the dark cortex panel fill frame — five lobes, and the **dashed feedback
edge looping from Learning back to Recall** along the bottom. Hold on the caption:
*"learning writes back to recall — every run leaves the brain different."*

> "**Backblaze isn't a bucket in this project — it's the long-term memory.** Every rejected
> attempt for this brand is sitting in B2 with the critique that rejected it. The Recall
> lobe reads that archive back and distils it into brand laws. **The storage layer is the
> training substrate.**"

**OPTIONAL — strongest visual in the whole video:** cut ~3s to your **B2 console tab**
showing `campaigns/{id}/runs/` and `brains/{slug}/`.

> "That's the bucket. Campaigns, every manifest, and the brain itself —
> `brains/slash brain-dot-json`, versioned."

---

## SHOT 6 — Provenance on reasoning · 1:32–1:45   🏷️ GENBLAZE

**NAVIGATE:** Stay on the Brain page. **Zoom the row of five status boxes directly
beneath the cortex graph** — `RECALL done` / `STRATEGY done 🔒0b74b890f2` /
`FORESIGHT done 🔒921e1509e3` / `LEARNING done 🔒334174ae7b`.

> "And the brain's own reasoning is provenance-tracked on the same footing as the art.
> **Every lobe is a Genblaze step with its own manifest in B2** — you can audit why it made
> a decision, not just what it made."

---

## SHOT 7 — 🎯 THE MOMENT · 1:45–2:08

**NAVIGATE:** Scroll down ~6 ticks. The **Foresight** panel is in the **right column**,
below *Measured self-improvement*.

**FRAME:** Zoom on `PREDICTED 87` — `vs` — `ACTUAL 85`, then drop to the grey
**`PREDICTED FAILURE MODE`** box below it.

> "Before spending a single generation call, the brain predicted 87. Actual: 85. And look
> what it predicted would go wrong — *'the key visual will drift too styled and
> design-forward.'* **That's the exact asset that failed critique.** It called its own weak
> point before generating anything."

**HOLD TWO SECONDS OF SILENCE on the failure-mode text.**

---

## SHOT 8 — Audience · 2:08–2:20

**NAVIGATE:** Same page, **left column** — *"Simulated audience reaction"*.

**FRAME:** Zoom the black `49/100 resonance` pill and `±13 spread`, then scroll to the
persona cards and stop on the one marked **`dislikes`**.

> "Four synthetic reviewers from the target audience. Real objections — *'subscriptions
> always sound gentle right up until they're hitting your card.'* Resonance 49. An honest
> number, and the laws it wrote reflect it."

---

## SHOT 9 — The advertisement · 2:20–2:42   🏷️ GENBLAZE ASYNC PROVIDER

**NAVIGATE:** Header → **`Current Kit`** → scroll the **left column** past the key visual
to the video card headed **`APPROVED ADVERTISEMENT · 3 SHOTS`** → **press play**.

**FRAME:** Let the ad play ~4s, then scroll just below to the **Storyboard** panel and
**pan left→right across the three shot cards** (HOOK / PRODUCT / BENEFIT), each showing
its own generated frame, camera direction and narration line.

> "And it doesn't make one image wobble for six seconds. Three separately generated
> scenes, each with its own camera move, cut together with the voiceover across it and a
> branded end card. **Video is a genuine async Genblaze provider — submit, poll, fetch —
> so all three shots render in parallel.** Six minutes becomes two."

---

## SHOT 10 — Close · 2:42–2:57   🏷️ BOTH

**NAVIGATE:** Scroll to the very bottom of the page — the footer reading
**`Genblaze Pipeline • Backblaze B2 Storage • Self-Critique & Retry Engine`**.

**FRAME:** Start on the footer badges, then push in slowly.

> "**Genblaze signs every asset — the manifest is embedded inside the MP4 itself,
> verifiable with no server. Backblaze keeps every attempt, every manifest, and the brain,
> forever.** Which means every failure this studio produces makes the next campaign better.
> Your storage bill becomes your competitive advantage."

---

# CUTTING ROOM

If you're over 3:00, sacrifice in this order:

1. **Shot 8** (audience) → trim to 8 seconds
2. **Shot 4** → drop entirely IF you show the B2 console in Shot 5 instead
3. **Shot 2** → shorten to 12 seconds

**Never cut Shot 7.** It's the climax.

---

# SPONSOR COVERAGE

| Shot | Backblaze | Genblaze |
|------|:---------:|:--------:|
| 1  Hook              | ✓  |    |
| 2  Pipeline          |    | ✓  |
| 3  Honest badge      |    |    |
| 4  Rejects kept      | ✓  | ✓  |
| 5  The Brain         | ✓✓ |    |
| 6  Lobe manifests    | ✓  | ✓✓ |
| 7  Foresight         |    |    |
| 8  Audience          |    |    |
| 9  The ad            |    | ✓  |
| 10 Close             | ✓✓ | ✓✓ |

Both sponsors are named in the **first 32 seconds** and the **last 15 seconds** —
the two spots judges actually remember.

---

# EDITING NOTES

1. **Zoom in on text, don't move the cursor.** Small UI type won't survive
   compression on Devpost/YouTube.
2. **Shot 7 is the climax.** Give it the silence.
3. Export at **1080p**. Verify final runtime is **under 3:00** before uploading.

---
---

# APPENDIX — DEVPOST SUBMISSION FIELDS

## Providers and models

```
TokenRouter (single gateway — all inference)
  • Image        bytedance-seed/seedream-4.5
  • Video        MiniMax-Hailuo-2.3  (image-to-video, async task queue)
  • Vision critique / copy / scripts / Campaign Brain
                 openai/gpt-5.4  (strict json_schema structured output)
  • Voiceover    openai/gpt-audio-mini

Deepgram
  • TTS fallback aura-2-thalia-en
  • STT          nova-3  — transcribes the generated voiceover back
                          to verify it matches the script (test assertion)

ElevenLabs
  • TTS fallback eleven_v3  (third in the automatic fallback chain)
```

## How the app uses Backblaze B2

```
B2 is the system of record AND the Campaign Brain's memory.

  campaigns/{id}/campaign.json     full campaign state
  campaigns/{id}/runs/...          every Genblaze manifest + asset,
                                   including REJECTED attempts
  campaigns/{id}/delivery/         deliverables with manifests embedded
  index/campaigns.json             library rollup
  brains/{slug}/brain.json         the brand's learned laws + run history
  brains/{slug}/v{n}.json          immutable snapshot of every brain version

Beyond storage, B2 is load-bearing in three ways:

1. LEARNING SUBSTRATE — the Recall lobe reads past rejected attempts and
   their critiques back out of B2 to write brand laws for the next campaign.
   Remove B2 and the product stops learning.

2. FALSIFIABILITY — versioned brain snapshots mean "the brain improved" is
   checkable against the brain as it actually was, not a mutable blob.

3. IMAGE-TO-VIDEO — each ad shot's generated first frame is presigned from
   the private bucket so the video provider can fetch it over https.

Accessed via S3StorageBackend.for_backblaze() — never boto3 directly.
```

## How the app uses Genblaze

```
Genblaze is the orchestration and provenance layer for every AI call.

  • Pipeline / Step / Run  — one Pipeline.run() per ATTEMPT, so each
    rejected attempt gets its own manifest instead of being overwritten.
    Retries chain via from_result(), recording parent_run_id lineage.

  • ObjectStorageSink (HIERARCHICAL keys) — one browsable tree per campaign.

  • Both provider styles, chosen by the upstream API:
      SyncProvider   — images, TTS, LLM calls (TokenRouterChatStep)
      BaseProvider   — video, a genuine submit/poll/fetch_output task queue

  • Manifests embedded IN the delivered media via genblaze_core.media —
    a downloaded MP4/JPEG/MP3 verifies on its own, with no server:
        get_handler("video/mp4").extract("ad.mp4").verify()  -> True

  • Even the Campaign Brain's own reasoning is a Genblaze step, so each
    lobe's decision carries a SHA-256 manifest.
```

## Judge-facing note (put this in the description)

```
The Library is pre-populated with completed campaigns — judges can evaluate
every feature (Campaign Brain, storyboard, provenance log, audience panel)
without spending generation quota. Hit "New Brief" to run one live; a full
campaign with the advertisement takes ~8 minutes.
```

## Submission checklist

- [ ] Deploy backend + frontend; **test the public URL in an incognito window**
- [ ] Grant `github.com/b2genblaze` contributor access if the repo is private
- [ ] README setup instructions current (already written)
- [ ] Demo video **under 3:00**
- [ ] Paste the four blocks above into Devpost
