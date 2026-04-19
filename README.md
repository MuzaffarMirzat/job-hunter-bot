# Job Hunter Bot

JSearch (RapidAPI) → filter → Discord webhook. Runs on a schedule (morning / evening UTC slots aligned with US Eastern) or via `workflow_dispatch`.

## Flow

1. **Session** — UTC hour `15` → `morning` (10 AM EST), hour `0` → `evening` (7 PM EST); other hours: heuristic for local runs.
2. **`posted_jobs.json`** — Created under `.data/` if missing (`{"job_ids": [], "last_updated": ""}`). Keeps the **last 500** ids in order; `last_updated` is set on each save.
3. **Search** — For each `SEARCH_KEYWORDS` entry: `fetch_jobs(keyword, "remote")` and `fetch_jobs(keyword, "united states")`, merged.
4. **`filter_jobs`** — Dedupe, title keywords (automation, SDET, QA, …), drop ids already in `posted_jobs.json` (re-exported from `src.jsearch` for convenience).
5. **Discord** — `send_header` → newest-first slice up to **`MAX_JOBS_PER_POST`** (default 15, max 25), one embed each with 0.5s spacing → `merge_posted_job_ids` → `send_summary`. If nothing to post: `send_no_jobs_message`.

## Files

| Path | Role |
|------|------|
| `src/main.py` | Orchestration |
| `src/jsearch.py` | `fetch_jobs`, `search_jobs`, `filter_jobs` |
| `src/job_filter.py` | `filter_jobs` implementation |
| `src/job_formatter.py` | `format_job_embed`, `format_header_message` |
| `src/discord_notifier.py` | `send_header`, `send_job_embed`, `send_summary`, `send_no_jobs_message` |
| `src/posted_state.py` | `posted_jobs.json` load / merge |
| `config/settings.py` | Env-backed settings |

## Local

```bash
cd job-hunter-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Create a **`.env`** (gitignored) with:

```bash
JSEARCH_API_KEY=your_key_here
DISCORD_WEBHOOK_URL=your_webhook_here
```

Optional: `SEARCH_KEYWORDS`, `MAX_JOBS_PER_POST` (default **15**, max 25), `POSTED_JOBS_FILE`, `JOB_SEARCH_DATE_POSTED`, `JOB_SEARCH_COUNTRY`, `JOB_SEARCH_NUM_PAGES`.

```bash
python src/main.py
```

## Deploy to GitHub Actions

Use this repo as the **root** of the GitHub project (so `.github/workflows/job_search.yml` and `src/main.py` paths match).

### After `git push` (finish setup)

1. **Actions permissions** — **Settings → Actions → General → Workflow permissions**  
   - Prefer **Read and write permissions** (needed for `actions/cache` to save `posted_jobs.json` between runs), **or** keep “Read repository contents” only if your org already grants `actions: write` via the workflow file (this repo sets `permissions.actions: write`).

2. **Repository secrets** — **Settings → Secrets and variables → Actions** → **Secrets** → **New repository secret**. Names must match **exactly** (case-sensitive):

   | Secret name | Value |
   |-------------|--------|
   | `JSEARCH_API_KEY` | RapidAPI key for JSearch |
   | `DISCORD_WEBHOOK_URL` | Discord incoming webhook URL |

3. **Default branch** — Scheduled cron only runs workflows from the **default** branch (usually `main`). **Settings → General** → confirm default branch is the one you pushed.

4. **Manual test** — **Actions** → **Job search notify** → **Run workflow** → branch `main` → **Run workflow**. Open the run, expand **Run job hunter**, confirm it exits **0** and Discord shows the bot.

5. **Schedules** — Cron runs at **15:00** and **00:00 UTC** daily (**10 AM** and **7 PM EST**). First run may wait until the next slot after you push.

6. **Optional variables** — **Settings → Secrets and variables → Actions** → **Variables** tab (not Secrets): `SEARCH_KEYWORDS`, `MAX_JOBS_PER_POST`, `JOB_SEARCH_DATE_POSTED`, `JOB_SEARCH_COUNTRY`, `JOB_SEARCH_NUM_PAGES`, `POSTED_JOBS_FILE` — only if you want overrides without code changes.

### First-time clone / push (reference)

```bash
cd job-hunter-bot
git remote add origin git@github.com:YOUR_USER/YOUR_REPO.git   # or HTTPS
# If origin already exists:
git remote set-url origin git@github.com:YOUR_USER/YOUR_REPO.git
git push -u origin main
```

Do **not** commit `.env` (gitignored). Local **`.data/`** is gitignored; CI keeps **`posted_jobs.json`** via **Actions cache**.

### Schedule (workflow file)

- **Cron:** `0 15 * * *` and `0 0 * * *` UTC → **10:00 AM** and **7:00 PM EST** (UTC−5). When US Eastern is on **EDT** (UTC−4), the same runs are **11:00 AM** and **8:00 PM** local.  
- **Python:** 3.11 on `ubuntu-latest`.

**Notes:** EST vs EDT shifts vs UTC; adjust crons if you need fixed Eastern clock times. **Forks** do not run scheduled workflows until enabled in the fork’s Actions settings. The workflow uses **actions/checkout@v6**, **actions/setup-python@v6**, and **actions/cache@v5** (Node.js 24–compatible; avoids GitHub’s Node 20 deprecation warnings on hosted runners).

**Self-hosted runners:** `actions/cache@v5` needs runner **v2.327.1** or newer ([cache release notes](https://github.com/actions/cache/releases)).
