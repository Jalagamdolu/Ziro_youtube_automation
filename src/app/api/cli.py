"""CLI behind `make video` and `make export`."""

import argparse
import shutil
import time
from pathlib import Path

from app.api.actions import CreateRequest, create_project, latest_artifacts
from app.core import config, db
from app.core.models import Project
from app.graph.stages import CANCELLED, DONE, FAILED, GATES

REVIEW_URL = "http://localhost:8000/ui/projects/{}"


def video(args: argparse.Namespace) -> None:
    project_id = create_project(CreateRequest(
        prompt=args.prompt, format=args.format, audience=args.audience, cta=args.cta,
    ))
    print(f"project {project_id}")
    seen = ""
    while True:
        with db.session() as s:
            status = s.get_one(Project, project_id).status
        if status != seen:
            seen = status
            print(f"status: {status}")
            if status in GATES:
                print(f"  review: {REVIEW_URL.format(project_id)}")
        if status in (args.until, DONE, FAILED, CANCELLED):
            return
        time.sleep(2)


def export(args: argparse.Namespace) -> None:
    """Copy the latest non-stale version of every artifact into DEST/<stage>/."""
    with db.session() as s:
        latest = latest_artifacts(s, args.run)
    for (stage, name), key in latest.items():
        target = args.dest / stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(config.runs_dir() / key, target)
    print(f"exported {len(latest)} files to {args.dest}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="ziro")
    commands = parser.add_subparsers(required=True)

    run = commands.add_parser("video")
    run.add_argument("--prompt", required=True)
    run.add_argument("--format", choices=["short", "long"], required=True)
    run.add_argument("--until", default="end", help="gate or stage to stop at, or 'end'")
    run.add_argument("--audience", default=CreateRequest.model_fields["audience"].default)
    run.add_argument("--cta", default=CreateRequest.model_fields["cta"].default)
    run.set_defaults(handler=video)

    out = commands.add_parser("export")
    out.add_argument("--run", required=True)
    out.add_argument("--dest", required=True, type=Path)
    out.set_defaults(handler=export)

    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
