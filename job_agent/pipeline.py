"""The steps the CLI and the chat agent share: search, score, write."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

from .config import Preferences
from .documents import save_application
from .knowledge_base import load_knowledge_base
from .linkedin import Job, LinkedInClient, LinkedInError, job_id_from_url
from .llm import Application, CareerModel, ClaudeError, FitScore
from .store import JobStore, filter_reason

Log = Callable[[str], None]


class JobAgent:
    def __init__(self, prefs: Preferences, kb_dir: Path, output_dir: Path, log: Log = print):
        self.prefs = prefs
        self.kb_dir = kb_dir
        self.log = log
        self.store = JobStore(output_dir)
        self.linkedin = LinkedInClient(prefs.search.request_delay_seconds)
        self._model: CareerModel | None = None

    @property
    def model(self) -> CareerModel:
        if self._model is None:  # loaded lazily so `search` works without an API key
            self._model = CareerModel(self.prefs, load_knowledge_base(self.kb_dir))
        return self._model

    def reload_knowledge_base(self) -> None:
        self._model = None

    # --- search -------------------------------------------------------------------------

    def search(
        self,
        keywords: list[str] | None = None,
        locations: list[str] | None = None,
        max_results: int | None = None,
    ) -> list[Job]:
        """Searches LinkedIn, fetches full descriptions for new jobs and stores those that pass filters."""
        s = self.prefs.search
        found: list[Job] = []
        for keyword in keywords or s.keywords:
            for location in locations or s.locations:
                self.log(f"Searching LinkedIn: '{keyword}' in '{location or 'anywhere'}'")
                try:
                    results = self.linkedin.search(
                        keyword, location, max_results or s.max_results_per_query,
                        posted_within_days=s.posted_within_days, workplace=s.workplace,
                        experience_levels=s.experience_levels, job_types=s.job_types,
                    )
                except LinkedInError as err:
                    self.log(f"  ! {err}")
                    continue
                new = [job for job in results if job.job_id not in self.store.records]
                self.log(f"  {len(results)} results, {len(new)} new")
                found.extend(self._ingest(job) for job in new)
                self.store.save()
        return [job for job in found if job and not self.store.records[job.job_id].get("filtered_out")]

    def _ingest(self, job: Job) -> Job:
        reason = filter_reason(job, self.prefs.filters)  # title/company filters before fetching
        if not reason:
            try:
                self.linkedin.fetch_details(job)
            except LinkedInError as err:
                self.log(f"  ! could not fetch description for {job.job_id}: {err}")
            reason = filter_reason(job, self.prefs.filters)
        self.store.add(job)
        if reason:
            self.store.records[job.job_id]["filtered_out"] = reason
        return job

    def add_job(self, url: str = "", description: str = "", title: str = "", company: str = "") -> Job:
        """Adds a job by LinkedIn URL, or by pasted description for any other site."""
        job_id = job_id_from_url(url) if url else None
        if job_id:
            job = self.store.job(job_id) if job_id in self.store.records else Job(job_id, title, company, "", url)
            if not description:
                self.linkedin.fetch_details(job)
        else:
            if not description:
                raise ValueError("Not a LinkedIn job URL — pass the job description text as well")
            digest = hashlib.sha1(f"{url}|{title}|{company}|{description}".encode()).hexdigest()
            job_id = f"manual-{digest[:10]}"
            job = Job(job_id, title or "Untitled role", company or "Unknown company", "", url, source="manual")
        if description:
            job.description = description
        self.store.add(job)
        self.store.update_job(job)
        self.store.save()
        return job

    # --- scoring & writing --------------------------------------------------------------------

    def score(self, job_id: str) -> FitScore:
        job = self.store.job(job_id)
        result = self.model.score(job)
        self.store.set_score(job_id, result.model_dump())
        self.store.save()
        return result

    def score_pending(self) -> None:
        pending = self.store.unscored()
        self.log(f"Scoring {len(pending)} job(s) with Claude")
        for job_id in pending:
            job = self.store.job(job_id)
            try:
                result = self.score(job_id)
            except ClaudeError as err:
                self.log(f"  ! {job.title} @ {job.company}: {err}")
                continue
            self.log(f"  {result.score:3d}  {job.title} @ {job.company}")

    def write(self, job_id: str, extra_instructions: str = "") -> tuple[Application, dict]:
        job = self.store.job(job_id)
        record = self.store.records[job_id]
        score = FitScore(**record["score"]) if record["score"] else None
        application = self.model.write_application(job, extra_instructions)
        paths = save_application(self.store.output_dir, job, application, score)
        self.store.set_documents(job_id, paths)
        self.store.save()
        return application, paths

    def run(self) -> None:
        """Full pipeline: search, score everything new, then write documents for the best matches."""
        self.search()
        self.score_pending()
        threshold = self.prefs.ranking.min_score
        todo = [
            (jid, r) for jid, r in self.store.ranked()
            if r["score"]["score"] >= threshold and not r["documents"]
        ][: self.prefs.documents.top_n]
        self.log(f"Writing documents for {len(todo)} job(s) scoring ≥ {threshold}")
        for job_id, record in todo:
            job = record["job"]
            self.log(f"  {job['title']} @ {job['company']}")
            try:
                _, paths = self.write(job_id)
            except ClaudeError as err:
                self.log(f"    ! {err}")
                continue
            self.log(f"    → {paths['folder']}")
