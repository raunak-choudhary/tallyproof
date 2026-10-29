# Analyst

The analyst turns a question into a typed query spec, compiles it to SQL pinned to a signed checkpoint, and lets the model write only a template whose values and citations are bound to the query's results. The verifier checks every draft before anyone sees it. The design is in [ADR-0009](../adr/0009-bound-claims-answer-format.md) and [ADR-0014](../adr/0014-constrained-query-ir.md).

This page is generated from the code's docstrings.

::: apps.analyst.query_spec

::: apps.analyst.compiler

::: apps.analyst.router

::: apps.analyst.answer

::: apps.analyst.pipeline

::: apps.analyst.sql_guard

::: apps.analyst.llm

::: apps.analyst.limits

::: apps.analyst.retrieval
