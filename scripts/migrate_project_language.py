"""CLI for migrating ArcReel projects to the English-only language contract."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from lib.project_translation import ProjectTranslator


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate ArcReel projects to English.")
    parser.add_argument("--projects-root", default="./projects", help="Projects root directory")
    parser.add_argument("--target-lang", default="en", help="Target language (only 'en' is supported)")
    parser.add_argument("--include-source", action="store_true", help="Translate source/*.txt and source/*.md files")
    parser.add_argument("--write", action="store_true", help="Apply changes in place. Without this flag the command errors.")
    parser.add_argument("--project", action="append", dest="projects", help="Specific project(s) to migrate")
    return parser


async def _run(args: argparse.Namespace) -> int:
    if not args.write:
        raise SystemExit("Refusing to run without --write. This migration performs an in-place project rewrite.")

    projects_root = Path(args.projects_root).resolve()
    translator = await ProjectTranslator.create(target_language=args.target_lang)

    if args.projects:
        project_dirs = [projects_root / name for name in args.projects]
    else:
        project_dirs = [
            path
            for path in sorted(projects_root.iterdir(), key=lambda item: item.name)
            if path.is_dir() and not path.name.startswith(".")
        ]

    if not project_dirs:
        print("No projects found.")
        return 0

    for project_dir in project_dirs:
        report = await translator.migrate_project(
            project_dir,
            include_source=args.include_source,
            write=True,
        )
        print(f"Migrated {report.project_name}")
        print(f"  backup: {report.backup_path}")
        for changed in report.changed_files:
            print(f"  changed: {changed}")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
