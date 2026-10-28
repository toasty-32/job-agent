"""Searches LinkedIn's public (logged-out) job listings.

Uses the same guest endpoints that power linkedin.com/jobs for visitors who are not signed in,
so no LinkedIn account or cookies are involved. Requests are deliberately slow and few; this is
meant for one person's job hunt, not bulk collection. LinkedIn's terms restrict automated
access — use it at your own discretion, and fall back to `add-job` (paste a URL or description)
if requests start being refused.
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
PAGE_SIZE = 10  # LinkedIn returns 10 cards per guest page

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

WORKPLACE = {"onsite": "1", "remote": "2", "hybrid": "3"}
EXPERIENCE = {
    "internship": "1", "entry": "2", "associate": "3",
    "mid_senior": "4", "director": "5", "executive": "6",
}
JOB_TYPE = {
    "full_time": "F", "part_time": "P", "contract": "C", "temporary": "T",
    "internship": "I", "volunteer": "V", "other": "O",
}


@dataclass
class Job:
    job_id: str
    title: str
    company: str
    location: str
    url: str
    posted: str = ""
    description: str = ""
    criteria: dict[str, str] = field(default_factory=dict)
    source: str = "linkedin"

    def to_dict(self) -> dict:
        return asdict(self)


class LinkedInError(RuntimeError):
    pass


def _codes(values: list[str], table: dict[str, str], name: str) -> str:
    unknown = [v for v in values if v not in table]
    if unknown:
        raise ValueError(f"Unknown {name} {unknown}; choose from {sorted(table)}")
    return ",".join(table[v] for v in values)


def build_search_params(
    keywords: str,
    location: str = "",
    posted_within_days: int | None = None,
    workplace: list[str] | None = None,
    experience_levels: list[str] | None = None,
    job_types: list[str] | None = None,
    start: int = 0,
) -> dict[str, str]:
    params = {"keywords": keywords, "location": location, "start": str(start)}
    if posted_within_days:
        params["f_TPR"] = f"r{int(posted_within_days) * 86400}"
    if workplace:
        params["f_WT"] = _codes(workplace, WORKPLACE, "workplace")
    if experience_levels:
        params["f_E"] = _codes(experience_levels, EXPERIENCE, "experience level")
    if job_types:
        params["f_JT"] = _codes(job_types, JOB_TYPE, "job type")
    return params


def _text(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""


def parse_search_results(html: str) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for card in soup.select("div.base-card, div.job-search-card"):
        urn = card.get("data-entity-urn", "")
        match = re.search(r"(\d+)$", urn)
        link = card.select_one("a.base-card__full-link")
        href = link.get("href", "") if link else ""
        if not match:
            match = re.search(r"-(\d+)(?:\?|$)", href)
        if not match:
            continue
        job_id = match.group(1)
        time_tag = card.select_one("time")
        jobs.append(
            Job(
                job_id=job_id,
                title=_text(card.select_one(".base-search-card__title")),
                company=_text(card.select_one(".base-search-card__subtitle")),
                location=_text(card.select_one(".job-search-card__location")),
                url=f"https://www.linkedin.com/jobs/view/{job_id}/",
                posted=time_tag.get("datetime", "") if time_tag else "",
            )
        )
    return jobs


def parse_job_detail(html: str) -> tuple[str, dict[str, str]]:
    """Returns (description text, criteria such as seniority / employment type)."""
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one(".show-more-less-html__markup, .description__text")
    if body:
        for br in body.find_all("br"):
            br.replace_with("\n")
        for li in body.find_all("li"):
            li.replace_with(f"\n- {_text(li)}\n")
        for block in body.find_all(["p", "div", "ul", "ol", "h1", "h2", "h3", "h4"]):
            block.append("\n\n")
        lines = (re.sub(r"[ \t]+", " ", line).strip() for line in body.get_text().splitlines())
        description = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    else:
        description = ""
    criteria = {}
    for item in soup.select(".description__job-criteria-item"):
        key = _text(item.select_one(".description__job-criteria-subheader"))
        value = _text(item.select_one(".description__job-criteria-text"))
        if key:
            criteria[key] = value
    return description, criteria


def job_id_from_url(url: str) -> str | None:
    for pattern in (r"currentJobId=(\d+)", r"/jobs/view/(?:[^/?]*-)?(\d+)"):
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


class LinkedInClient:
    def __init__(self, delay_seconds: float = 2.5, session: requests.Session | None = None):
        self.delay = delay_seconds
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)
        self._last_request = 0.0

    def _get(self, url: str) -> str:
        for attempt in range(4):
            wait = self.delay - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
            response = self.session.get(url, timeout=30)
            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(self.delay * 2 ** (attempt + 1))
                continue
            if response.status_code == 400 and "seeMoreJobPostings" in url:
                return ""  # LinkedIn answers 400 past the last page of results
            if response.status_code != 200:
                raise LinkedInError(f"LinkedIn returned HTTP {response.status_code} for {url}")
            return response.text
        raise LinkedInError(f"LinkedIn kept rate-limiting requests to {url}; try again later")

    def search(self, keywords: str, location: str = "", max_results: int = 25, **filters) -> list[Job]:
        jobs: dict[str, Job] = {}
        start = 0
        while len(jobs) < max_results:
            params = build_search_params(keywords, location, start=start, **filters)
            page = parse_search_results(self._get(f"{SEARCH_URL}?{urlencode(params)}"))
            new = [j for j in page if j.job_id not in jobs]
            if not new:
                break
            for job in new:
                jobs[job.job_id] = job
            start += PAGE_SIZE
        return list(jobs.values())[:max_results]

    def fetch_details(self, job: Job) -> Job:
        html = self._get(DETAIL_URL.format(job_id=job.job_id))
        job.description, job.criteria = parse_job_detail(html)
        if not job.title:  # jobs added by URL have no search card to take these from
            soup = BeautifulSoup(html, "html.parser")
            job.title = _text(soup.select_one(".top-card-layout__title, h2"))
            job.company = _text(soup.select_one(".topcard__org-name-link, .topcard__flavor"))
            job.location = _text(soup.select_one(".topcard__flavor--bullet"))
        return job
