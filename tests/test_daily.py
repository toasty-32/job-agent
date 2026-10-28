import builtins
import os

from job_agent.config import Preferences
from job_agent.env import load_env_file
from job_agent.knowledge_base import load_knowledge_base
from job_agent.linkedin import Job
from job_agent.llm import CareerModel
from job_agent.pipeline import JobAgent
from job_agent.review import review
from job_agent.summary import render_summary

from test_pipeline import ROOT, FakeClient, make_prefs


def make_agent(tmp_path, client):
    prefs = Preferences.load(make_prefs(tmp_path))
    agent = JobAgent(prefs, ROOT / "knowledge_base", tmp_path / "out", log=lambda _: None)
    agent._model = CareerModel(prefs, load_knowledge_base(ROOT / "knowledge_base"), client=client)
    agent.search = lambda *a, **k: []  # no network in tests
    return agent


def test_daily_reports_each_suitable_job_once(tmp_path):
    agent = make_agent(tmp_path, FakeClient())
    agent.store.add(Job("111", "Scientist", "Acme", "Boston", "https://x/111", description="d"))
    path = agent.daily()
    html = path.read_text(encoding="utf-8")
    assert "1 new job scored" in html and "Acme" in html and "Review jobs" in html
    assert (tmp_path / "out" / "latest-summary.html").exists()

    second = agent.daily().read_text(encoding="utf-8")
    assert "No new jobs" in second and "1 earlier suggestion is still waiting" in second


def test_summary_escapes_job_text():
    record = {
        "job": {"title": "<script>x</script>", "company": "A&B", "location": "", "url": "https://x?a=1&b=2", "posted": ""},
        "score": {"score": 90, "verdict": "strong", "summary": "s", "matching_strengths": [], "gaps": [], "dealbreakers": []},
    }
    html = render_summary([("1", record)], 0, 65, "2026-10-28")
    assert "<script>x" not in html and "&lt;script&gt;" in html and "A&amp;B" in html


def test_review_writes_approved_and_learns_from_skips(tmp_path, monkeypatch):
    client = FakeClient()
    agent = make_agent(tmp_path, client)
    for job_id in ("1", "2"):
        agent.store.add(Job(job_id, f"Role {job_id}", "Acme", "Boston", f"https://x/{job_id}", description="d"))
        agent.score(job_id)
    answers = iter(["a", "lead with pipelines", "s", "too junior"])
    monkeypatch.setattr(builtins, "input", lambda _: next(answers))
    review(agent)

    records = agent.store.records
    assert records["1"]["status"] == "approved" and records["1"]["documents"]
    assert records["2"]["status"] == "skipped" and not records["2"]["documents"]
    assert "lead with pipelines" in client.calls[-1]["messages"][0]["content"]
    assert agent.store.awaiting_review(0) == []

    history = agent.store.feedback_history()
    assert "Not interested — Role 2 at Acme (Boston): too junior" in history
    model = CareerModel(agent.prefs, load_knowledge_base(ROOT / "knowledge_base"), client=client, feedback=history)
    assert "<candidate_feedback>" in model.system[0]["text"] and "too junior" in model.system[0]["text"]


def test_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("JOB_AGENT_TEST_KEY", raising=False)
    monkeypatch.setenv("JOB_AGENT_KEEP", "real")
    (tmp_path / ".env").write_text('﻿# comment\nJOB_AGENT_TEST_KEY="abc"\nJOB_AGENT_KEEP=fromfile\n', encoding="utf-8")
    load_env_file(tmp_path / ".env")
    assert os.environ["JOB_AGENT_TEST_KEY"] == "abc"
    assert os.environ["JOB_AGENT_KEEP"] == "real"
    monkeypatch.delenv("JOB_AGENT_TEST_KEY")


def test_daily_command_writes_error_page_without_preferences(tmp_path):
    from job_agent.__main__ import main

    status = main(["--preferences", str(tmp_path / "missing.yaml"), "--output", str(tmp_path / "out"), "daily"])
    assert status == 1
    assert "preferences.yaml" in (tmp_path / "out" / "latest-summary.html").read_text(encoding="utf-8")
