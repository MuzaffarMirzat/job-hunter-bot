# Job Hunter Bot

JSearch (RapidAPI) → filter → Discord webhook. Runs on a schedule (morning / evening UTC slots aligned with US Eastern) or via `workflow_dispatch`.

## Flow

1. **Session** — UTC hour `13` → `morning`, hour `23` → `evening` (other hours: heuristic for local runs).
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

Use the **`job-hunter-bot` folder as the repository root** (so `.github/workflows/` and `src/main.py` paths match the workflow).

1. **Create the repo on GitHub** (empty, no README) and copy the remote URL, e.g. `https://github.com/YOU/job-hunter-bot.git`.

2. **From your machine**, in this folder:

   ```bash
   cd job-hunter-bot
   git init
   git add .
   git commit -m "Add job hunter bot and GitHub Actions workflow"
   git branch -M main
   git remote add origin https://github.com/YOU/job-hunter-bot.git
   git push -u origin main
   ```

   Do **not** commit `.env`; it is listed in `.gitignore`. Posted-job state lives under `.data/` (also ignored); **Actions restores/saves** `.data/posted_jobs.json` via cache between runs.

3. **Repository secrets** — GitHub → **Settings → Secrets and variables → Actions → New repository secret**:

   | Name | Value |
   |------|--------|
   | `JSEARCH_API_KEY` | Your RapidAPI key for JSearch |
   | `DISCORD_WEBHOOK_URL` | Your Discord incoming webhook URL |

4. **Enable Actions** — **Settings → Actions → General**: allow Actions (default for new repos is usually fine).

5. **Test** — **Actions** tab → **Job search notify** → **Run workflow** → **Run workflow**. Open the run log to confirm it finished without errors and check Discord.

### Schedule (already in the workflow)

- **Cron:** `0 13 * * *` and `0 23 * * *` UTC (roughly morning / evening US Eastern in standard time).  
- **Python:** 3.11 on `ubuntu-latest`.  
- **Optional repo variables** (same tab, **Variables**): `SEARCH_KEYWORDS`, `MAX_JOBS_PER_POST`, `JOB_SEARCH_DATE_POSTED`, `JOB_SEARCH_COUNTRY`, `JOB_SEARCH_NUM_PAGES`, `POSTED_JOBS_FILE` — only if you want to override defaults without changing code.

**Note:** EST vs EDT shifts relative to UTC; tweak the cron expressions if you need fixed local clock times year-round.
