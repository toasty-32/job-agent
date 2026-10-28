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

## Setup

```bash
cd job-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp preferences.example.yaml preferences.yaml      # then edit it
export ANTHROPIC_API_KEY=sk-ant-...               # or `ant auth login`
```

Then fill `knowledge_base/` with your material: profile, full career history, projects, old CVs
(`.docx` or `.pdf`), publications and so on. `knowledge_base/README.md` has tips. Delete
`example_profile.md` when you're done. Your personal files, `preferences.yaml` and `output/` are
git-ignored.

## Usage

**One-shot pipeline.** This searches, scores every new job, and writes documents for the
top `documents.top_n` jobs that score at least `ranking.min_score`:

```bash
python -m job_agent run
```

**Chat mode.** The agent decides which tools to use:

```bash
python -m job_agent chat
```
```
you › find remote ML engineer roles in Europe posted this week and score them
you › write applications for the top two, emphasise my leadership experience
you › add this one: https://www.linkedin.com/jobs/view/4012345678/
```

**Individual steps:**

| Command | What it does |
|---|---|
| `search` | Searches LinkedIn for every keyword × location, fetches descriptions, applies filters. No Claude calls. |
| `score` | Scores every saved job that has no score yet. |
| `list [--min-score N]` | Lists saved jobs, best first. |
| `add-job <linkedin-url>` | Saves a specific LinkedIn job. |
| `add-job <url> --description-file jd.txt --title ... --company ...` | Saves a job from any other site. |
| `write <job_id> [--instructions "..."]` | Writes the CV and cover letter for one job. |

Every job and its score is kept in `output/jobs.json`. Jobs you've already seen are skipped on
later runs, so a daily `run` only handles new postings.

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
