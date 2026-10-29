import runpy
from pathlib import Path
from types import SimpleNamespace

import config.env

CONF = Path(__file__).resolve().parents[2] / "config" / "gunicorn_conf.py"


def test_the_api_runs_threaded_workers_sized_from_settings(monkeypatch):
    settings = SimpleNamespace(api_workers=3, api_threads=6)
    monkeypatch.setattr(config.env, "app_settings", lambda: settings)
    conf = runpy.run_path(str(CONF))
    assert (conf["worker_class"], conf["workers"], conf["threads"]) == ("gthread", 3, 6)
