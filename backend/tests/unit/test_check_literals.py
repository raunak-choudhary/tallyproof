import importlib.util
from pathlib import Path

from config.env import REPO_ROOT

spec = importlib.util.spec_from_file_location(
    "check_literals", REPO_ROOT / "scripts" / "ci" / "check_literals.py"
)
assert spec is not None
assert spec.loader is not None
check_literals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_literals)


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_hardcoded_urls_hosts_and_model_ids_are_found(tmp_path):
    write(
        tmp_path,
        "backend/apps/x/client.py",
        'BASE = "http://127.0.0.1:8000"\nMODEL = "claude-sonnet-5-5"\n',
    )
    write(tmp_path, "frontend/src/api.ts", 'const api = "https://api.example.org";\n')
    found = check_literals.scan(tmp_path)
    assert found == [
        "backend/apps/x/client.py:1: 'http://127.0.0.1:8000'",
        "backend/apps/x/client.py:2: 'claude-sonnet-5-5'",
        "frontend/src/api.ts:1: 'https://api.example.org'",
    ]


def test_settings_docstrings_comments_tests_and_waivers_are_allowed(tmp_path):
    write(tmp_path, "backend/config/env.py", 'URL = "http://127.0.0.1:18081"\n')
    write(tmp_path, "backend/apps/x/docs.py", '"""See https://c2sp.org/signed-note."""\n')
    write(tmp_path, "backend/apps/x/tests/test_a.py", 'URL = "http://localhost"\n')
    write(
        tmp_path, "backend/apps/x/safe.py", 'HOSTS = {"localhost"}  # literal-ok: the rule itself\n'
    )
    write(tmp_path, "frontend/src/a.ts", "// see https://example.org\nconst x = 1;\n")
    write(tmp_path, "frontend/src/a.test.ts", 'const u = "http://localhost:3000";\n')
    assert check_literals.scan(tmp_path) == []
