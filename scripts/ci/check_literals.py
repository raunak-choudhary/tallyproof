"""Fail if application code hardcodes a URL, a local address, or a model ID.

Environment-specific values belong in the settings modules, which read them from
the environment. This check keeps them there: it reads every string literal in the
backend and frontend source, skipping docstrings, comments, tests, migrations, and
the settings modules themselves.

Usage:
    python scripts/ci/check_literals.py
"""

import ast
import re
import sys
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PYTHON_ROOTS = (
    "backend/apps",
    "backend/config",
    "backend/tallyproof_core",
    "backend/tallyproof_pipeline",
)
TYPESCRIPT_ROOTS = ("frontend/src",)

SETTINGS_FILES = frozenset(
    {
        "backend/config/env.py",
        "backend/tallyproof_pipeline/settings.py",
    }
)
"""Where defaults for environment-specific values are allowed to live."""

ALLOWED = frozenset(
    {
        "http://json-schema.org/draft-07/schema#",  # a schema identifier, not an address
    }
)

FORBIDDEN = re.compile(
    r"[a-z][a-z0-9+.-]*://"  # any URL scheme
    r"|\blocalhost\b"
    r"|\b127\.0\.0\.1\b"
    r"|\bclaude-(?:opus|sonnet|haiku|fable|instant|\d)"
    r"|\bgpt-\d",
    re.IGNORECASE,
)
WAIVER = "literal-ok:"
"""A comment with this marker and a reason allows a literal on that line."""


def _skipped(relative: str) -> bool:
    parts = Path(relative).parts
    return (
        relative in SETTINGS_FILES
        or relative.startswith("backend/config/settings/")
        or "migrations" in parts
        or "tests" in parts
        or "__pycache__" in parts
        or ".test." in Path(relative).name
    )


def _docstring_nodes(tree: ast.AST) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                found.add(id(body[0].value))
    return found


def python_findings(path: Path, source: str) -> Iterator[tuple[int, str]]:
    """String literals in a Python file that look environment-specific."""
    tree = ast.parse(source, filename=str(path))
    docstrings = _docstring_nodes(tree)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and node.value not in ALLOWED
            and FORBIDDEN.search(node.value)
            and WAIVER not in lines[node.lineno - 1]
        ):
            yield node.lineno, node.value


def _ts_strings(source: str) -> Iterator[tuple[int, str]]:
    """Yield (line, body) for each string literal, skipping comments correctly."""
    i, line, n = 0, 1, len(source)
    while i < n:
        char = source[i]
        if char == "\n":
            line += 1
            i += 1
        elif source.startswith("//", i):
            end = source.find("\n", i)
            i = n if end == -1 else end
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            end = n if end == -1 else end + 2
            line += source.count("\n", i, end)
            i = end
        elif char in "\"'`":
            start_line, j, body = line, i + 1, []
            while j < n and source[j] != char:
                if source[j] == "\\" and j + 1 < n:
                    body.append(source[j : j + 2])
                    j += 2
                    continue
                if source[j] == "\n":
                    line += 1
                body.append(source[j])
                j += 1
            yield start_line, "".join(body)
            i = j + 1
        else:
            i += 1


def typescript_findings(source: str) -> Iterator[tuple[int, str]]:
    """String literals in a TypeScript file that look environment-specific."""
    lines = source.splitlines()
    for line, body in _ts_strings(source):
        if body not in ALLOWED and FORBIDDEN.search(body) and WAIVER not in lines[line - 1]:
            yield line, body


def scan(root: Path = ROOT) -> list[str]:
    """Every offending literal as ``path:line: value``."""
    problems: list[str] = []
    for top, pattern in [
        *((r, "*.py") for r in PYTHON_ROOTS),
        *((r, "*.ts*") for r in TYPESCRIPT_ROOTS),
    ]:
        for path in sorted((root / top).rglob(pattern)):
            relative = path.relative_to(root).as_posix()
            if _skipped(relative):
                continue
            source = path.read_text(encoding="utf-8")
            found = (
                python_findings(path, source)
                if path.suffix == ".py"
                else typescript_findings(source)
            )
            problems.extend(f"{relative}:{line}: {value!r}" for line, value in found)
    return problems


def main() -> int:
    """Print each hardcoded value and exit non-zero if there are any."""
    problems = scan()
    for problem in problems:
        print(problem)
    if problems:
        print(
            f"\n{len(problems)} hardcoded URL, address, or model ID literals. Move them to"
            " backend/config/env.py or tallyproof_pipeline/settings.py, or to a NEXT_PUBLIC_"
            " variable in the frontend."
        )
        return 1
    print("No hardcoded URLs, local addresses, or model IDs outside the settings modules.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
