"""Interactive review: approve or skip suggested jobs, then write documents for the approved ones."""
from __future__ import annotations

import textwrap

from .llm import ClaudeError
from .pipeline import JobAgent

CHOICES = {"a": "approved", "s": "skipped", "l": "later"}


def _ask(prompt: str, allowed: str) -> str:
    while True:
        answer = input(prompt).strip().lower()[:1]
        if answer in allowed:
            return answer
        print(f"  Please type one of: {', '.join(allowed)}")


def review(agent: JobAgent) -> None:
    queue = agent.store.awaiting_review(agent.prefs.ranking.min_score)
    if not queue:
        print("Nothing to review. New suggestions appear after the next daily search.")
        return
    print(f"{len(queue)} job(s) to review, best first.\n")
    approved: list[tuple[str, str]] = []
    for index, (job_id, record) in enumerate(queue, 1):
        job, score = record["job"], record["score"]
        print("=" * 72)
        print(f"[{index}/{len(queue)}]  {score['score']}/100  {job['title']}")
        print(f"         {job['company']} · {job['location']}")
        print(f"         {job['url']}")
        print(textwrap.fill(score["summary"], 72, initial_indent="  ", subsequent_indent="  "))
        for gap in score["gaps"] + score["dealbreakers"]:
            print(f"  gap: {gap}")
        choice = _ask("\n  [a]pply  [s]kip  [l]ater  [q]uit reviewing > ", "aslq")
        if choice == "q":
            break
        note = ""
        if choice == "a":
            note = input("  Anything to emphasise in the CV / letter? (Enter for none) > ").strip()
            approved.append((job_id, note))
        elif choice == "s":
            note = input("  Why not? This teaches future scoring (Enter to skip) > ").strip()
        agent.store.set_decision(job_id, CHOICES[choice], note)
        agent.store.save()
        print()

    if not approved:
        print("No jobs approved this time.")
        return
    print(f"\nWriting CVs and cover letters for {len(approved)} job(s). This takes a minute or two each.")
    for job_id, note in approved:
        job = agent.store.records[job_id]["job"]
        print(f"  {job['title']} @ {job['company']} ...", flush=True)
        try:
            _, paths = agent.write(job_id, note)
        except ClaudeError as err:
            print(f"    ! {err}")
            continue
        print(f"    saved to {paths['folder']}")
