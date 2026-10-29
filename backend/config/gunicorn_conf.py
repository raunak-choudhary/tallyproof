"""Gunicorn settings for the HTTP API, from the same settings as everything else.

Threaded workers: an analyst question can wait tens of seconds on the model, and
with sync workers it would hold a whole process. Each process answers at most
``ANALYST_MAX_INFLIGHT`` questions at once and keeps serving other requests on its
remaining threads.

Run from ``backend/``: ``gunicorn config.wsgi -c config/gunicorn_conf.py``.
"""

from config.env import app_settings

_settings = app_settings()

worker_class = "gthread"
workers = _settings.api_workers
threads = _settings.api_threads
