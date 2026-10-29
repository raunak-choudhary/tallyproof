# ADR-0021: One OpenAI-compatible model client, running on Groq's free tier

- Status: Accepted
- Date: 2026-10-28
- Supersedes: the brief's default of the Claude API with two model tiers

## Context

The brief's default for the analyst's model was the Claude API, with a cheaper model for routing and a stronger one for answers. The project has no budget for a paid key, and every claim it makes must be reproducible by anyone who clones it. The analyst's design also leaves the model little to do that's hard: it fills in a typed query spec from a fixed catalog, and writes a short template using labels it's given. It never writes SQL on the main path and never types a number ([ADR-0009](0009-bound-claims-answer-format.md), [ADR-0014](0014-constrained-query-ir.md)).

Most hosted models now serve the OpenAI chat-completions protocol, including Google Gemini, Groq, OpenRouter, Together, and a local Ollama.

## Decision

The analyst talks to its model through one small client (`backend/apps/analyst/llm.py`) over the OpenAI chat-completions protocol, with plain HTTPS and no vendor SDK. The provider, base URL, key, model IDs, and reasoning effort are settings. Structured output is requested as a JSON schema, and the server validates every reply itself.

The live provider is Groq's free tier running `openai/gpt-oss-120b` with low reasoning effort, the same model for routing and answers. Router and answer model IDs stay separate settings, so two tiers remain one setting away.

## Reasons

- **Free, and anyone can reproduce it.** A reader can create a free key and run the same evaluation.
- **Provider-independent.** Changing provider is five settings. The evaluation table records the model IDs of every run, so comparing providers is a configuration change, not a code change.
- **Small surface.** About 300 lines with retries, `Retry-After` handling, pacing, a response cache, and run budgets, all tested without a network.
- **The model's job is narrow.** With the query spec and the slot-bound composer, the evaluation measures whether the route and the spec are right, which a mid-size open model does well: the smoke set passes every gate.

## Alternatives considered

- **The Claude API, two tiers.** The brief's default. It needs a paid key; the client supports any OpenAI-compatible endpoint, so it's a settings change if a key becomes available.
- **Gemini's free tier.** Tried first. It allows 20 requests a day per model, far below the roughly 550 a full evaluation needs, and its newer models spend their output allowance on reasoning unless the effort is set low.
- **A local model through Ollama.** Free and private, but the 8 GB laptop already shares its memory between Spark and the container VM, and small local models follow a JSON schema poorly.
- **A vendor SDK.** Each pulls in its own dependencies and ties the code to one provider.

## Consequences

- Groq's free tier allows 1,000 requests and 200,000 tokens a day per model. A full evaluation of every question spans three nights; the smoke set fits easily. Both limits are documented in [limitations](../limitations.md).
- A provider retiring a model invalidates every recorded response at once, because the model ID is part of each cache key. Re-recording is one command with a key.
- Prompts go to a third party. They hold only public USAspending records and regulation text, and the threat model says so.
