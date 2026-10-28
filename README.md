# Job Agent

A personal agent that searches LinkedIn for jobs that match your preferences, scores each one
against your background, and writes a tailored CV and cover letter for the best matches. Every
fact in those documents comes from your own **knowledge base**. It runs on Claude.

```
preferences.yaml ──► LinkedIn search ──► local filters ──► Claude fit score (0–100)
                                                              │
knowledge_base/  ──────────────────────────────────────────► Claude writes CV + cover letter
                                                              │
                                     output/applications/<company>--<role>--<id>/
                                        cv.md · cv.docx · cover_letter.md · cover_letter.docx · notes.md
```

## Setup on Windows (recommended)

1. Install **Python 3.10+** from https://www.python.org/downloads/. Tick **"Add python.exe to PATH"**.
2. Download this project: `git clone https://github.com/toasty-32/job-agent` (or use GitHub's
   **Code → Download ZIP** and unzip it somewhere permanent, such as `Documents\job-agent`).
3. Double-click **`Install (Windows).cmd`** in the project folder. It will:
   - install the packages into a private `.venv` folder
   - ask for your Claude API key **once** and save it in `.env`, readable only by your account
   - ask what time to run the daily search, then add it to Windows Task Scheduler
   - put **Review jobs**, **Search jobs now** and **Job agent folder** shortcuts on your desktop
   - open `preferences.yaml` and the `knowledge_base` folder so you can fill them in
4. Edit `preferences.yaml`. Put your CVs, career history and project notes in `knowledge_base\`,
   then delete `example_profile.md`.
5. Double-click **Search jobs now** to try it.

To remove the schedule and shortcuts, run
`powershell -ExecutionPolicy Bypass -File scripts\uninstall-windows.ps1`.

## The daily routine

1. **Every day at your chosen time** the agent searches LinkedIn, scores each new job against
   your knowledge base and preferences, and **opens a summary page in your browser**. It lists the
   new jobs that scored at least `ranking.min_score`, each with a link, why it fits, and its gaps. If the
   PC was off or asleep at that time, the search runs once it's back on. Past summaries are kept in
   `output\summaries\`, and logs in `output\logs\`.
2. **When you're ready, double-click Review jobs.** For each suggested job, press **a** (apply),
   **s** (skip) or **l** (later):
   - *apply*: optionally say what to emphasise ("lead with my team leadership").
   - *skip*: optionally say why ("too junior", "don't want big pharma"). The agent reads these
     reasons on every later run and scores similar jobs the way you would.
3. Once you've worked through the list, it **writes a tailored CV and cover letter for every job you
   approved** and opens the `applications` folder.

## Setup on macOS / Linux

```bash
cd job-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp preferences.example.yaml preferences.yaml      # then edit it
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env        # saved once, loaded automatically
```

To schedule it, add a cron entry such as
`0 8 * * * cd /path/to/job-agent && .venv/bin/python -m job_agent daily`.

## Commands

Run these as `python -m job_agent <command>`. On Windows, use `.venv\Scripts\python -m job_agent <command>`
from the project folder.

| Command | What it does |
|---|---|
| `daily [--open]` | Search, score, and write today's summary page. This is what the schedule runs. |
| `review` | Approve or skip suggested jobs, then write documents for the approved ones. |
| `chat` | Talk to the agent and let it use all the tools, e.g. *"find remote roles in Europe and score them"*. |
| `run` | Search, score, then write documents for the top `documents.top_n` jobs automatically, with no review. |
| `search` | Search LinkedIn and save new jobs, with no Claude calls. |
| `score` | Score every saved job that has no score yet. |
| `list [--min-score N]` | List saved jobs, best first. |
| `add-job <linkedin-url>` | Save a specific LinkedIn job. |
| `add-job <url> --description-file jd.txt --title ... --company ...` | Save a job from any other site. |
| `write <job_id> [--instructions "..."]` | Write the CV and cover letter for one job. |

Every job, score and decision is kept in `output/jobs.json`, so each job is only suggested once.
Each application lands in `output/applications/<company>--<role>--<id>/` as `cv.docx`,
`cover_letter.docx`, Markdown copies, and `notes.md`. The notes give the fit score, your gaps, and
any requirements your knowledge base has no evidence for.

## How it works

- **`job_agent/linkedin.py`** uses LinkedIn's public guest job pages, the ones logged-out
  visitors see, with the filters from your preferences (date posted, remote/hybrid/on-site,
  seniority, job type). It needs no account or cookies, waits between requests, and backs off
  on rate limits.
- **`job_agent/llm.py`** sends one stable system prompt (rules, your preferences and the full
  knowledge base) on every call, and that prompt is prompt-cached. Scoring a batch of jobs
  therefore re-reads your background at cached-token prices. Scores and documents come back as
  structured output (Pydantic models), so they always parse. The prompt forbids inventing facts,
  and each `notes.md` lists the job requirements your knowledge base has no evidence for.
- Your apply/skip decisions and reasons are added to that system prompt, so scoring learns your taste.
- **`job_agent/agent.py`** is the chat agent. It runs a tool-use loop over `search_linkedin`,
  `list_jobs`, `get_job`, `add_job`, `score_job`, `write_application` and `reload_knowledge_base`.
- If Claude's safety classifiers decline a request, requests use `fallbacks: "default"`, which
  re-runs it on Anthropic's recommended fallback model.

Model and effort are set in `preferences.yaml` under `claude:`. The default model is
`claude-opus-5-5`, with `low` effort for scoring and `high` for writing.

## Caveats

- **LinkedIn's terms of service prohibit automated access.** This tool keeps volume low and
  uses only public pages, but LinkedIn may still rate-limit or block requests, or change its
  page markup (the parser lives in `linkedin.py`). You use it at your own risk. If searches
  start failing, find jobs by hand and use `add-job`. The rest of the pipeline works the same.
- Always proofread before sending. The agent is told to use only facts from your knowledge base,
  but you are the final check.

## Tests

```bash
pytest
```

The tests run offline. They use HTML fixtures for the LinkedIn parser and a fake Claude client
for the pipeline.
