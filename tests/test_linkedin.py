from pathlib import Path

import pytest

from job_agent.linkedin import (
    Job, LinkedInClient, build_search_params, job_id_from_url, parse_job_detail, parse_search_results,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_search_results():
    jobs = parse_search_results((FIXTURES / "search.html").read_text())
    assert [j.job_id for j in jobs] == ["4012345678", "4087654321"]
    first = jobs[0]
    assert first.title == "Senior Computational Biologist"
    assert first.company == "Acme Bio"
    assert first.location == "Boston, MA"
    assert first.posted == "2026-10-25"
    assert first.url == "https://www.linkedin.com/jobs/view/4012345678/"


def test_parse_job_detail():
    description, criteria = parse_job_detail((FIXTURES / "detail.html").read_text())
    assert "Join our oncology team." in description
    assert "Build single-cell pipelines." in description
    assert "- PhD in a quantitative field" in description
    assert criteria == {"Seniority level": "Mid-Senior level", "Employment type": "Full-time"}


def test_build_search_params():
    params = build_search_params(
        "data scientist", "Remote", posted_within_days=7, workplace=["remote", "hybrid"],
        experience_levels=["mid_senior"], job_types=["full_time", "contract"], start=20,
    )
    assert params == {
        "keywords": "data scientist", "location": "Remote", "start": "20",
        "f_TPR": "r604800", "f_WT": "2,3", "f_E": "4", "f_JT": "F,C",
    }
    with pytest.raises(ValueError):
        build_search_params("x", workplace=["moon"])


@pytest.mark.parametrize("url,expected", [
    ("https://www.linkedin.com/jobs/view/4012345678/", "4012345678"),
    ("https://www.linkedin.com/jobs/view/senior-scientist-at-acme-4012345678?trk=x", "4012345678"),
    ("https://www.linkedin.com/jobs/search/?currentJobId=4099999999&keywords=x", "4099999999"),
    ("https://example.com/careers/123", None),
])
def test_job_id_from_url(url, expected):
    assert job_id_from_url(url) == expected


class FakeResponse:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


class FakeSession:
    def __init__(self, pages):
        self.pages, self.urls, self.headers = list(pages), [], {}

    def get(self, url, timeout):
        self.urls.append(url)
        return self.pages.pop(0)


def test_search_paginates_and_stops_on_empty_page():
    page = (FIXTURES / "search.html").read_text()
    session = FakeSession([FakeResponse(200, page), FakeResponse(400)])
    jobs = LinkedInClient(0, session).search("biologist", "Boston", max_results=25)
    assert len(jobs) == 2
    assert "start=0" in session.urls[0] and "start=10" in session.urls[1]


def test_fetch_details_fills_missing_card_fields():
    session = FakeSession([FakeResponse(200, (FIXTURES / "detail.html").read_text())])
    job = LinkedInClient(0, session).fetch_details(Job("4012345678", "", "", "", "u"))
    assert job.title == "Senior Computational Biologist"
    assert job.company == "Acme Bio"
    assert job.criteria["Employment type"] == "Full-time"
