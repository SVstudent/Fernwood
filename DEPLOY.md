# Deploying Fernwood

Frontend → **Vercel**. Backend → **Render** (free, Docker, stable https hostname).

Total time: ~25 minutes. Do **STEP 0 only after you have finished recording your
demo video** — it edits a file the local backend auto-reloads.

---

## STEP 0 — The one code change deployment needs

The deployed frontend calls the backend from a *different origin*, so the API has
to allow it. Without this, every request is blocked by the browser — including the
SSE stream, which shows up as **a run that starts and then goes silent**. It is
the single most likely thing to break a first deploy.

### 0a. `backend/app/config.py`

Add this field to `Settings`, just above the `public_api_base` comment:

```python
    # Extra browser origins allowed to call this API, comma-separated. Required
    # once the frontend is deployed: it then calls the backend cross-origin, and
    # without its exact origin here every request fails CORS — including the SSE
    # stream, which surfaces as a run that starts and then goes silent.
    # Vercel PREVIEW deployments get a new hostname per commit, so main.py also
    # allows *.vercel.app by regex rather than needing this updated every push.
    fernwood_allowed_origins: str = ""
```

### 0b. `backend/app/main.py`

Add the settings import:

```python
from app.config import get_settings
```

Then replace the whole `app.add_middleware(CORSMiddleware, ...)` block with:

```python
# In development the Vite server proxies /api here, so CORS is unused. In
# production the frontend is served from another origin entirely (Vercel) and
# calls this API directly — so the deployed origin MUST be allowed or every
# request fails, including the SSE stream, which looks like a run that starts
# and then silently stops.
#
# allow_origin_regex covers Vercel preview deployments, which mint a new
# hostname per commit; pinning those by hand would break on every push.
_dev_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
]
_configured = [
    origin.strip()
    for origin in get_settings().fernwood_allowed_origins.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[*_dev_origins, *_configured],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    # The media endpoint serves video with Range requests; browsers need these
    # exposed or seeking in the <video> player breaks.
    expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
)
```

Verify locally (localhost still works exactly as before):

```bash
cd backend && uv run pytest -q -m "not live"
curl -s localhost:8787/api/health | python3 -m json.tool
```

---

## STEP 1 — Push to GitHub

```bash
git add -A
git commit -m "feat: Campaign Brain, multi-shot advertisement track, deploy configs"
git push
```

`.gitignore` already excludes `.env`, so no secrets ship. `.env.example` is
committed as the template.

> **Private repo?** Grant `https://github.com/b2genblaze` contributor access:
> Settings → Collaborators → Add people → `b2genblaze`.

---

## STEP 2 — Backend on Render

1. [dashboard.render.com](https://dashboard.render.com) → **New** → **Blueprint**
2. Connect the repo. Render reads `render.yaml` and configures everything.
3. It will prompt for the secrets marked `sync: false`:

   | Variable | Value |
   |---|---|
   | `TOKENROUTER_API_KEY` | from your `.env` |
   | `B2_KEY_ID` | from your `.env` |
   | `B2_APP_KEY` | from your `.env` |
   | `DEEPGRAM_API_KEY` | from your `.env` (optional) |
   | `ELEVENLABS_API_KEY` | from your `.env` (optional) |
   | `FERNWOOD_ALLOWED_ORIGINS` | leave blank for now — set in Step 4 |

4. Deploy. First build ~5 min (Docker + `uv sync`).
5. Note the URL, e.g. `https://fernwood-backend.onrender.com`

**Verify before continuing:**

```bash
curl -s https://YOUR-BACKEND.onrender.com/api/health | python3 -m json.tool
```

Expect `"ok": true`, `"mode": "b2"`, and `"warnings": []`. If storage says
`local`, `FERNWOOD_STORAGE` didn't apply — fix it before deploying the frontend,
or campaigns will vanish on every redeploy.

---

## STEP 3 — Frontend on Vercel

```bash
npm i -g vercel
vercel login
vercel --prod
```

Or via the dashboard: **Add New → Project → import the repo**. `vercel.json`
sets the framework, build command and output directory.

**Set the environment variable** (Project → Settings → Environment Variables):

| Name | Value |
|---|---|
| `VITE_API_BASE` | `https://YOUR-BACKEND.onrender.com` |

> This must be set **before** the build — Vite inlines `import.meta.env` at
> build time, so adding it afterwards does nothing until you redeploy.

Redeploy after setting it. Note your URL, e.g. `https://fernwood.vercel.app`

---

## STEP 4 — Close the CORS loop

Back in Render → **Environment** → set:

```
FERNWOOD_ALLOWED_ORIGINS = https://fernwood.vercel.app
```

Save. Render restarts automatically (~30s).

---

## STEP 5 — Verify like a judge

Open your Vercel URL **in an incognito window** and check:

- [ ] Library loads with campaigns (this proves B2 reads work cross-origin)
- [ ] Open a campaign → key visual image renders (media proxy + CORS)
- [ ] Advertisement plays, and **seeking works** (Range requests + exposed headers)
- [ ] Campaign Brain page loads with lobes, laws and audience panel
- [ ] DevTools console is clean — **no CORS errors**

If the Library is empty but `/api/health` is fine, it's almost always
`FERNWOOD_ALLOWED_ORIGINS` not matching your exact origin (scheme + host, no
trailing slash).

---

## Free-tier realities worth knowing

| Behaviour | Impact | What to do |
|---|---|---|
| Render sleeps after ~15 min idle | First hit takes ~50s | Load the URL once before demoing or sharing |
| 512 MB RAM | Fine — images are downscaled to 1024px before critique | — |
| Ephemeral disk | Irrelevant: everything lives in B2 | Just never set `FERNWOOD_STORAGE=local` |
| A live run costs real quota | Judges clicking *New Brief* spends money | Say so in the Devpost description (below) |

**Put this in your Devpost description:**

> The Library is pre-populated with completed campaigns — judges can evaluate
> every feature (Campaign Brain, storyboard, provenance log, audience panel)
> without spending generation quota. Hit "New Brief" to run one live; a full
> campaign with the advertisement takes ~8 minutes.

---

## Alternatives to Render

Both work with the same `backend/Dockerfile`:

**Fly.io** — better for long-running SSE, no sleep on paid; free allowance is small.

```bash
cd backend && fly launch --no-deploy
fly secrets set TOKENROUTER_API_KEY=... B2_KEY_ID=... B2_APP_KEY=... \
  FERNWOOD_STORAGE=b2 FERNWOOD_ALLOWED_ORIGINS=https://your-app.vercel.app
fly deploy
```

**Railway** — simplest UI, $5 trial credit. New Project → Deploy from repo →
set root directory to `backend`, add the same variables.

> Whichever you pick: **one instance / one worker only.** The SSE run registry
> is in-process, so a second instance means a browser can connect to a process
> that has never heard of its run, and the campaign appears to hang forever.
