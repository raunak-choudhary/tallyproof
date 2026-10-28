"""Check that every commit in a range follows Conventional Commits.

Pull requests are rebase-merged, so every commit lands on main as written.
Checking only the pull request title would let badly formatted commits through.

Usage:
    python scripts/ci/check_commit_messages.py origin/main..HEAD
"""

import re
import subprocess
import sys

TYPES = "feat|fix|docs|test|refactor|perf|build|ci|chore|revert"
SUBJECT = re.compile(rf"^({TYPES})(\([a-z0-9-]+\))?!?: \S.*$")
MAX_SUBJECT_LENGTH = 100


def subjects(revision_range: str) -> list[tuple[str, str]]:
    """Return (short hash, subject) pairs for every commit in the range."""
    output = subprocess.run(  # noqa: S603 - fixed git command, range comes from CI config
        ["git", "log", "--format=%h%x00%s", revision_range],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [tuple(line.split("\x00", 1)) for line in output.splitlines() if line]  # type: ignore[misc]


def problems(subject: str) -> list[str]:
    """Return what is wrong with one commit subject, or nothing if it is valid."""
    found = []
    if not SUBJECT.match(subject):
        found.append(f"does not match '<type>(<scope>): <summary>' with type in {TYPES}")
    if len(subject) > MAX_SUBJECT_LENGTH:
        found.append(f"is {len(subject)} characters; the limit is {MAX_SUBJECT_LENGTH}")
    return found


def main() -> int:
    """Check the commit range given on the command line."""
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    failures = 0
    for short_hash, subject in subjects(sys.argv[1]):
        for problem in problems(subject):
            failures += 1
            print(f"{short_hash} {subject!r} {problem}")
    if failures:
        print(f"\n{failures} problem(s) found. See CONTRIBUTING.md for the commit format.")
        return 1
    print("All commit messages follow Conventional Commits.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
