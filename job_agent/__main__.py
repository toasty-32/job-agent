"""Command line entry point: python -m job_agent <command>."""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

from .config import DEFAULT_KB_DIR, DEFAULT_OUTPUT_DIR, DEFAULT_PREFERENCES, ROOT, Preferences
from .env import load_env_file
from .pipeline import JobAgent


def _open(path: Path) -> None:
    """Opens a file or folder with its default app (Windows / macOS / Linux)."""
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - local file the agent just wrote
    else:
        import subprocess
        import webbrowser

        if path.is_dir():
            subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(path)], check=False)
        else:
            webbrowser.open(path.resolve().as_uri())


def _daily(agent: JobAgent, output: Path, open_summary: bool) -> int:
    """Run by the scheduled task, often with no console, so everything also goes to a log file."""
    from .summary import write_error_page

    log_dir = output / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{date.today().isoformat()}.log"

    def log(message: str) -> None:
        line = f"{datetime.now():%H:%M:%S} {message}"
        print(line)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    agent.log = log
    try:
        summary = agent.daily()
        status = 0
    except Exception:
        log(traceback.format_exc())
        summary = write_error_page(output, traceback.format_exc())
        status = 1
    if open_summary:
        _open(summary)
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="job_agent", description=__doc__)
    parser.add_argument("--preferences", type=Path, default=DEFAULT_PREFERENCES)
    parser.add_argument("--knowledge-base", type=Path, default=DEFAULT_KB_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    commands = parser.add_subparsers(dest="command", required=True)

    daily = commands.add_parser("daily", help="search and score new jobs, then write today's summary page")
    daily.add_argument("--open", action="store_true", help="open the summary in the browser when done")
    review = commands.add_parser("review", help="approve or skip suggested jobs; writes documents for approved ones")
    review.add_argument("--pause", action="store_true", help="wait for Enter before exiting (for the desktop shortcut)")
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
    load_env_file(ROOT / ".env")
    try:
        prefs = Preferences.load(args.preferences)
    except (FileNotFoundError, ValueError) as err:
        print(err, file=sys.stderr)
        if args.command == "daily":  # the scheduled run has no console, so show it in the browser
            from .summary import write_error_page

            page = write_error_page(args.output, str(err))
            if args.open:
                _open(page)
        return 1
    agent = JobAgent(prefs, args.knowledge_base, args.output)

    if args.command == "daily":
        return _daily(agent, args.output, args.open)
    elif args.command == "review":
        from .review import review

        try:
            review(agent)
            applications = args.output / "applications"
            if args.pause and applications.exists():
                _open(applications)
        except Exception:
            traceback.print_exc()
            print("\nSomething went wrong. Copy the error above and paste it to Claude for help.")
        finally:
            if args.pause:
                input("\nPress Enter to close this window.")
    elif args.command == "run":
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
