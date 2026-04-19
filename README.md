# Job Hunter Bot

Job data from **JSearch** or **[JOBS SEARCH API](https://rapidapi.com/rphrp1985/api/jobs-search-api)** (RapidAPI) → filter → Discord webhook. The workflow sets **`JOB_SEARCH_PROVIDER=jobs_search`** by default so you can stay under JSearch quota; switch to **`jsearch`** when your JSearch allowance resets. Defaults target **BASIC / free-tier** usage (low request volume). Runs on a **once-daily** schedule (10 AM EST) or via `workflow_dispatch`.

## Flow

1. **Session** — UTC hour `15` → `morning` (10 AM EST), hour `0` → `evening` (7 PM EST); other hours: heuristic for local runs.
2. **`posted_jobs.json`** — Created under `.data/` if missing (`{"job_ids": [], "last_updated": ""}`). Keeps the **last 500** ids in order; `last_updated` is set on each save.
3. **Search** — For each keyword (capped by **`JSEARCH_MAX_KEYWORDS`**, default **3**) and each **`FETCH_LOCATIONS`** entry (default **`remote`** only), the configured provider’s `fetch_jobs` merges results (normalized to one shape for filters and Discord).
4. **`filter_jobs`** — Dedupe, title keywords (automation, SDET, QA, …), drop ids already in `posted_jobs.json` (re-exported from `src.jsearch` for convenience).
5. **Discord** — `send_header` → newest-first slice up to **`MAX_JOBS_PER_POST`** (default 15, max 25), one embed each with 0.5s spacing → `merge_posted_job_ids` → `send_summary`. If nothing to post: `send_no_jobs_message`.

## Files

| Path | Role |
|------|------|
| `src/main.py` | Orchestration |
| `src/jsearch.py` | JSearch: `fetch_jobs`, `search_jobs`; `filter_jobs` re-export |
| `src/jobs_search_api.py` | JOBS SEARCH API: POST `/getjobs`, `fetch_jobs`, `search_jobs`, quota exception |
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

Optional: `JOB_SEARCH_PROVIDER` (`jsearch` or `jobs_search`), `SEARCH_KEYWORDS`, `MAX_JOBS_PER_POST` (default **15**, max 25), `POSTED_JOBS_FILE`, `JOB_SEARCH_DATE_POSTED`, `JOB_SEARCH_COUNTRY`, `JOB_SEARCH_NUM_PAGES`.

### Free / BASIC tier (default behavior)

Rough monthly upstream requests ≈ **`JSEARCH_MAX_KEYWORDS` × len(`FETCH_LOCATIONS`) × `JOB_SEARCH_NUM_PAGES` × scheduled runs per month`** (plus manual runs). Each provider has its own RapidAPI quota (JOBS SEARCH API Basic is typically **~100 requests/month** — check the listing). Defaults keep this small:

| Setting | Default | Purpose |
|---------|---------|--------|
| `FETCH_LOCATIONS` | `remote` | Skips `united states` (add it only if your plan has headroom). |
| `JSEARCH_MAX_KEYWORDS` | `3` | Only the first N keywords from `SEARCH_KEYWORDS` each run. Set to **`all`** for no cap (paid tiers). |
| Schedule | Once daily (10 AM EST) | Second cron is **commented out** in the workflow; uncomment only if quota allows. |

On **HTTP 429** with no data, the bot posts a Discord **notice** (no traceback spam).

**Paid / higher quota:** set `JSEARCH_MAX_KEYWORDS=all`, `FETCH_LOCATIONS=remote,united states`, and uncomment the evening cron in `.github/workflows/job_search.yml`.

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

5. **Schedules** — By default cron runs **once** at **15:00 UTC** (**10 AM EST**). First run may wait until the next slot after you push.

6. **Optional variables** — **Settings → Secrets and variables → Actions** → **Variables** tab (not Secrets): `SEARCH_KEYWORDS`, `JSEARCH_MAX_KEYWORDS`, `FETCH_LOCATIONS`, `MAX_JOBS_PER_POST`, `JOB_SEARCH_DATE_POSTED`, `JOB_SEARCH_COUNTRY`, `JOB_SEARCH_NUM_PAGES`, `POSTED_JOBS_FILE` — only if you want overrides without code changes. Source selection is **`JOB_SEARCH_PROVIDER`** in the workflow file (`jobs_search` vs `jsearch`).

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

- **Cron (default):** `0 15 * * *` UTC → **10:00 AM EST** (UTC−5; **11 AM** local when EDT). Optional second line in the YAML is **commented** for free-tier quota.  
- **Python:** 3.11 on `ubuntu-latest`.

**Notes:** EST vs EDT shifts vs UTC; adjust crons if you need fixed Eastern clock times. **Forks** do not run scheduled workflows until enabled in the fork’s Actions settings. The workflow uses **actions/checkout@v6**, **actions/setup-python@v6**, and **actions/cache@v5** (Node.js 24–compatible; avoids GitHub’s Node 20 deprecation warnings on hosted runners).

**Self-hosted runners:** `actions/cache@v5` needs runner **v2.327.1** or newer ([cache release notes](https://github.com/actions/cache/releases)).

**If “Cache save failed”:** the workflow saves under a **new key each run** (`…-${{ github.run_id }}`) and restores via `restore-keys` so GitHub does not reject overwriting the same key you just restored. If it still fails, set **Settings → Actions → General → Workflow permissions** to **Read and write** (org policy can block cache writes even when the YAML sets `actions: write`).
