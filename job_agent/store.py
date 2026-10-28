"""A small JSON file that remembers every job seen, its score and generated documents."""
from __future__ import annotations

import json
from pathlib import Path

from .config import FilterPrefs
from .linkedin import Job


class JobStore:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.path = output_dir / "jobs.json"
        self.records: dict[str, dict] = {}
        if self.path.exists():
            self.records = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.records, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def add(self, job: Job) -> bool:
        """Stores a job; returns False if it was already known."""
        if job.job_id in self.records:
            return False
        self.records[job.job_id] = {"job": job.to_dict(), "score": None, "documents": None}
        return True

    def job(self, job_id: str) -> Job:
        if job_id not in self.records:
            raise KeyError(f"Unknown job id {job_id}. Run `search` or `add-job` first.")
        return Job(**self.records[job_id]["job"])

    def update_job(self, job: Job) -> None:
        self.records[job.job_id]["job"] = job.to_dict()

    def set_score(self, job_id: str, score: dict) -> None:
        self.records[job_id]["score"] = score

    def set_documents(self, job_id: str, documents: dict) -> None:
        self.records[job_id]["documents"] = documents

    def unscored(self) -> list[str]:
        return [jid for jid, r in self.records.items() if r["score"] is None and not r.get("filtered_out")]

    def ranked(self) -> list[tuple[str, dict]]:
        scored = [(jid, r) for jid, r in self.records.items() if r["score"]]
        return sorted(scored, key=lambda item: item[1]["score"]["score"], reverse=True)


def filter_reason(job: Job, filters: FilterPrefs) -> str | None:
    """Cheap local filters applied before spending tokens on scoring."""
    company = job.company.lower()
    title = job.title.lower()
    for name in filters.exclude_companies:
        if name.lower() in company:
            return f"excluded company '{name}'"
    for word in filters.exclude_title_keywords:
        if word.lower() in title:
            return f"title contains excluded keyword '{word}'"
    if filters.required_keywords and job.description:
        haystack = f"{title}\n{job.description.lower()}"
        if not any(word.lower() in haystack for word in filters.required_keywords):
            return "none of the required keywords appear"
    return None
