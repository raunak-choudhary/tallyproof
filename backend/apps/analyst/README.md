# analyst

Answers questions about the ledger with numbers bound to query results and citations the browser can verify. It's being built in stages; today it holds the views the analyst reads.

| Module | What it does |
|---|---|
| `migrations/0001_views.py` | The curated `analyst` views: obligations, outlays, awards, cash movements, breaks, journal, and policy sections. Descriptions are a separate view because they're untrusted source text |

The `tallyproof_analyst` role can read these views and nothing else. Its connections are read-only by default, time out after 3 seconds, and have `search_path` pinned to `analyst` (`infra/postgres/create-roles.sql`). Even with read-only mode switched off, it holds no grant that allows a write.

Tests: `tests/integration/analyst/`.
