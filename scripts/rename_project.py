#!/usr/bin/env python3
"""Rename the starter to your own product name.

Rewrites the human-readable name ("Django SaaS Starter") and the slug
("django-saas-starter") in text files. Dry-run by default; pass --apply to write.

    python scripts/rename_project.py "Acme Cloud"            # preview
    python scripts/rename_project.py "Acme Cloud" --apply    # do it

The ``config`` and ``apps`` Python packages are left alone on purpose (see
docs/customizing.md). LICENSE, CHANGELOG.md, .git, .env and virtualenvs are
never touched.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

OLD_NAME = "Django SaaS Starter"
OLD_SLUG = "django-saas-starter"

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "staticfiles",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}
SKIP_FILES = {
    "LICENSE",
    "CHANGELOG.md",
    ".env",
    "db.sqlite3",
    ".coverage",
    "rename_project.py",
    "test_rename_project.py",
}
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,40}$")


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def iter_text_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or SKIP_DIRS & set(path.relative_to(root).parts) or path.name in SKIP_FILES:
            continue
        yield path


def plan_changes(root: Path, new_name: str, new_slug: str) -> list[tuple[Path, str, int]]:
    """Return (path, new_text, replacement_count) for every file that would change."""
    changes = []
    for path in iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: skip
        count = text.count(OLD_NAME) + text.count(OLD_SLUG)
        if count:
            changes.append((path, text.replace(OLD_NAME, new_name).replace(OLD_SLUG, new_slug), count))
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("name", help='New display name, e.g. "Acme Cloud"')
    parser.add_argument("--slug", help="New slug (default: derived from the name)")
    parser.add_argument("--apply", action="store_true", help="Write changes (default is a dry run)")
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent.parent, help=argparse.SUPPRESS
    )
    args = parser.parse_args(argv)

    name = args.name.strip()
    slug = args.slug or slugify(name)
    if not name or "\n" in name or not SLUG_RE.match(slug):
        print(f"error: invalid name or slug (slug must match {SLUG_RE.pattern}): {slug!r}", file=sys.stderr)
        return 2
    if slug == OLD_SLUG or name == OLD_NAME:
        print("error: the new name must differ from the current one", file=sys.stderr)
        return 2

    changes = plan_changes(args.root, name, slug)
    for path, _, count in changes:
        print(f"{'rewrite' if args.apply else 'would rewrite'}: {path.relative_to(args.root)} ({count})")
    if args.apply:
        for path, text, _ in changes:
            path.write_text(text, encoding="utf-8")
        print(f"Done: {len(changes)} file(s) updated. Review with `git diff`.")
    else:
        print(f"Dry run: {len(changes)} file(s) would change. Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
