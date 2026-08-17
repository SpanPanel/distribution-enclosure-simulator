#!/usr/bin/env python3
"""Reject private issue-tracker IDs in lines this commit adds.

This repository's issue tracker lives outside it, so an ID like ``DESIM-3on``
means nothing to anyone reading the public repository, and `CHANGELOG.md` ships
inside the sdist to PyPI, where it cannot be amended after upload. Reference
GitHub issues (``#26``) and handles (``@user``) instead, or just describe the
work.

Only *added* lines are checked, so the IDs already present in older files are
grandfathered and editing those files for unrelated reasons stays possible. The
rule is about not adding more.

Prefixes are listed explicitly rather than matched by shape. A general
``[A-Z]+-[a-z0-9]+`` pattern flags ordinary prose like ``MQTT-based``, and a
check that cries wolf gets disabled, which is worse than no check. Add a prefix
here when a new tracker appears.
"""

from __future__ import annotations

import re
import subprocess
import sys

PREFIXES = ("DESIM", "SPEC", "TOOLS", "SDK", "UMS")

# `PREFIX-<base36>` with optional dotted sub-issue parts: DESIM-3on, DESIM-a5p.15.1.
_ID = re.compile(rf"\b(?:{'|'.join(PREFIXES)})-[0-9a-z]{{2,8}}(?:\.[0-9a-z]+)*\b")

# A file may legitimately discuss the convention itself.
_EXEMPT_PATHS = ("scripts/check_no_tracker_ids.py",)


def main() -> int:
    diff = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--no-color"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout

    path = ""
    hits: list[tuple[str, str]] = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        if path in _EXEMPT_PATHS:
            continue
        for found in _ID.findall(line):
            hits.append((path, found))

    if not hits:
        return 0

    print("Private tracker IDs in added lines:\n", file=sys.stderr)
    for path, found in dict.fromkeys(hits):
        print(f"  {path}: {found}", file=sys.stderr)
    print(
        "\nThese mean nothing to a public reader, and CHANGELOG.md ships to PyPI\n"
        "where it cannot be amended. Use a GitHub issue number (#26) or describe\n"
        "the work instead. Existing occurrences in older files are grandfathered;\n"
        "this only rejects lines being added.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
