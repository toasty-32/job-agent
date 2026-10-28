"""Command line entry point: python -m job_agent <command>."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import DEFAULT_KB_DIR, DEFAULT_OUTPUT_DIR, DEFAULT_PREFERENCES, Preferences
from .pipeline import JobAgent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="job_agent", description=__doc__)
    parser.add_argument("--preferences", type=Path, default=DEFAULT_PREFERENCES)
    parser.add_argument("--knowledge-base", type=Path, default=DEFAULT_KB_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("run", help="search, score, and write documents for the best new matches")
    commands.add_parser("chat", help="talk to the agent and let it use the tools")
    commands.add_parser("search", help="search LinkedIn and save new jobs (no Claude calls)")
    commands.add_parser("score", help="score every saved job that has no score yet")

    ls = commands.add_parser("list", help="show saved jobs, best first")
    ls.add_argument("--min-score", type=int, default=0)

    add = commands.add_parser("add-job", help="save a job by LinkedIn URL or pasted description")
    add.add_argument("url", nargs="?", default="")
    add.add_argument("--description-file", type=Path, help="text file with the job description")
    add.add_argument("--title", default="")
    add.add_argument("--company", default="")

    write = commands.add_parser("write", help="write a CV and cover letter for one job")
    write.add_argument("job_id")
    write.add_argument("--instructions", default="", help='e.g. "emphasise people management"')

    args = parser.parse_args(argv)
    try:
        prefs = Preferences.load(args.preferences)
    except (FileNotFoundError, ValueError) as err:
        print(err, file=sys.stderr)
        return 1
    agent = JobAgent(prefs, args.knowledge_base, args.output)

    if args.command == "run":
        agent.run()
    elif args.command == "chat":
        from .agent import chat

        chat(agent)
    elif args.command == "search":
        jobs = agent.search()
        print(f"Saved {len(jobs)} new job(s). Run `score` next, or `list` to see them.")
    elif args.command == "score":
        agent.score_pending()
    elif args.command == "list":
        for job_id, record in agent.store.ranked():
            score = record["score"]
            if score["score"] >= args.min_score:
                job = record["job"]
                done = " ✓docs" if record["documents"] else ""
                print(f"{score['score']:3d}  {job['title']} — {job['company']} ({job['location']})  [{job_id}]{done}")
        unscored = agent.store.unscored()
        if unscored:
            print(f"\n{len(unscored)} job(s) not scored yet — run `score`.")
    elif args.command == "add-job":
        description = args.description_file.read_text(encoding="utf-8") if args.description_file else ""
        job = agent.add_job(args.url, description, args.title, args.company)
        print(f"Saved {job.title} — {job.company} as [{job.job_id}]")
    elif args.command == "write":
        application, paths = agent.write(args.job_id, args.instructions)
        print(f"Saved to {paths['folder']}")
        for req in application.unsupported_requirements:
            print(f"  gap: {req}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
