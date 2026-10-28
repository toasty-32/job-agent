"""Interactive chat agent: Claude drives the search / score / write tools on your behalf."""
from __future__ import annotations

import json

from anthropic import beta_tool

from .linkedin import LinkedInError
from .llm import FALLBACK_BETA, ClaudeError
from .pipeline import JobAgent

AGENT_INSTRUCTIONS = """\
You are now chatting with the candidate directly. Use your tools to search LinkedIn, inspect
and score jobs, and write applications. Search terms and locations default to the preferences,
but follow the candidate's lead when they ask for something different. Before writing documents
for a job, make sure it has been scored, and mention any serious gaps. Keep replies short and
scannable: job lists as `score · title · company · location · job_id`."""


def _summary(agent: JobAgent, job_id: str) -> dict:
    record = agent.store.records[job_id]
    job = record["job"]
    return {
        "job_id": job_id,
        "title": job["title"],
        "company": job["company"],
        "location": job["location"],
        "posted": job["posted"],
        "url": job["url"],
        "score": record["score"]["score"] if record["score"] else None,
        "filtered_out": record.get("filtered_out"),
        "documents": record["documents"]["folder"] if record["documents"] else None,
    }


def build_tools(agent: JobAgent) -> list:
    @beta_tool
    def search_linkedin(keywords: str = "", location: str = "", max_results: int = 10) -> str:
        """Search LinkedIn's public job listings and save new jobs (with full descriptions).
        Leave keywords/location empty to use every search from the candidate's preferences.

        Args:
            keywords: Job search terms, e.g. "computational biologist".
            location: City, region or country, e.g. "Boston, Massachusetts, United States".
            max_results: Maximum jobs per keyword/location pair.
        """
        jobs = agent.search(
            [keywords] if keywords else None, [location] if location else None, max_results
        )
        return json.dumps([_summary(agent, j.job_id) for j in jobs])

    @beta_tool
    def list_jobs(min_score: int = 0, include_unscored: bool = True, limit: int = 25) -> str:
        """List saved jobs, best scores first.

        Args:
            min_score: Only include scored jobs at or above this score.
            include_unscored: Also list jobs that have not been scored yet.
            limit: Maximum number of jobs to return.
        """
        rows = [_summary(agent, jid) for jid, r in agent.store.ranked() if r["score"]["score"] >= min_score]
        if include_unscored:
            rows += [_summary(agent, jid) for jid in agent.store.unscored()]
        return json.dumps(rows[:limit])

    @beta_tool
    def get_job(job_id: str) -> str:
        """Get a saved job's full description, criteria and score details.

        Args:
            job_id: The job's id.
        """
        record = agent.store.records.get(job_id)
        if record is None:
            raise KeyError(f"Unknown job id {job_id}")
        return json.dumps({**record["job"], "score": record["score"], "documents": record["documents"]})

    @beta_tool
    def add_job(url: str = "", description: str = "", title: str = "", company: str = "") -> str:
        """Save a job the candidate found themselves: a LinkedIn job URL, or any posting's text.

        Args:
            url: LinkedIn job URL (description is fetched automatically) or any other link.
            description: Full job description text; required when the URL is not LinkedIn.
            title: Job title (for non-LinkedIn jobs).
            company: Company name (for non-LinkedIn jobs).
        """
        job = agent.add_job(url, description, title, company)
        return json.dumps(_summary(agent, job.job_id))

    @beta_tool
    def score_job(job_id: str) -> str:
        """Score a saved job's fit (0-100) against the knowledge base and preferences, and save it.

        Args:
            job_id: The job's id.
        """
        return agent.score(job_id).model_dump_json()

    @beta_tool
    def write_application(job_id: str, extra_instructions: str = "") -> str:
        """Write a tailored CV and cover letter for a saved job; saves .md and .docx files.

        Args:
            job_id: The job's id.
            extra_instructions: Optional candidate requests, e.g. "emphasise leadership".
        """
        application, paths = agent.write(job_id, extra_instructions)
        return json.dumps({
            "folder": paths["folder"],
            "tailoring_notes": application.tailoring_notes,
            "unsupported_requirements": application.unsupported_requirements,
            "cover_letter_preview": application.cover_letter_markdown[:1200],
        })

    @beta_tool
    def reload_knowledge_base() -> str:
        """Re-read the knowledge base folder after the candidate has added or edited files."""
        agent.reload_knowledge_base()
        return "Reloaded. Note: the change applies to scoring and writing tools; restart chat to refresh this conversation's copy."

    return [search_linkedin, list_jobs, get_job, add_job, score_job, write_application, reload_knowledge_base]


def chat(agent: JobAgent) -> None:
    model = agent.model
    tools = build_tools(agent)
    by_name = {tool.name: tool for tool in tools}
    system = [
        {"type": "text", "text": model.system[0]["text"]},
        {"type": "text", "text": AGENT_INSTRUCTIONS, "cache_control": {"type": "ephemeral"}},
    ]
    messages: list = []
    print("Job agent ready. Try: 'find new jobs and write applications for the best two'. Ctrl-D to quit.\n")
    while True:
        try:
            user_input = input("you › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not user_input:
            continue
        messages.append({"role": "user", "content": user_input})
        while True:
            response = model.client.beta.messages.create(
                model=model.model,
                max_tokens=16000,
                system=system,
                tools=[tool.to_dict() for tool in tools],
                messages=messages,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
            messages.append({"role": "assistant", "content": response.content})
            for block in response.content:
                if block.type == "text" and block.text.strip():
                    print(f"\nagent › {block.text}\n")
            if response.stop_reason == "refusal":
                print("agent › (Claude declined that request)\n")
                break
            if response.stop_reason != "tool_use":
                break
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                print(f"  · {block.name}({json.dumps(block.input)[:120]})")
                try:
                    output = by_name[block.name].call(block.input)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
                except (KeyError, ValueError, LinkedInError, ClaudeError) as err:
                    results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": f"Error: {err}", "is_error": True,
                    })
            messages.append({"role": "user", "content": results})
