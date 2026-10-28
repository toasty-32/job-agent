# Knowledge base

Everything the agent knows about you lives in this folder. CVs and cover letters are written
**only** from facts found here — the agent is instructed never to invent employers, dates,
degrees, numbers or skills.

Drop in any mix of:

| Format | Examples |
|---|---|
| `.md` / `.txt` | profile, career history, project write-ups, achievements, publications |
| `.yaml` / `.yml` / `.json` | structured data (skills, education, certifications) |
| `.docx` / `.pdf` | your existing CVs, old cover letters, performance reviews, reference letters |

Sub-folders are fine. Files whose names start with `_` or `.` are ignored, as is this README.

Tips for better documents:

- **More raw material beats polish.** List every project with the problem, what *you* did, the
  tools, and the measurable result. The agent picks what's relevant per job.
- **Include numbers** (dataset sizes, % improvements, team sizes, budgets) — it will only quote
  numbers that appear here.
- **Add a `style.md`** with phrases you like/dislike, or a past cover letter you were proud of.
- Everything except this README and `example_profile.md` is git-ignored, so your personal data
  stays local. Delete `example_profile.md` once you've added your own files.
