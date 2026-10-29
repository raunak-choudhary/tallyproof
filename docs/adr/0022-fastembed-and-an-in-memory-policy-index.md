# ADR-0022: fastembed and an in-memory index for policy retrieval

- Status: Accepted
- Date: 2026-10-28
- Supersedes: the brief's default of local sentence-transformers, and the planned `doc_chunk` table with a pgvector column

## Context

Policy questions are answered from Federal Acquisition Regulation text, published into the ledger as one `policy.published` leaf per section. The corpus is four FAR parts: 289 sections, about 700 chunks. Retrieval needs to find the section a question is about so the answer can quote it exactly and cite the leaf that holds it.

The brief's default was a small BGE-class model through sentence-transformers, with chunks and vectors in Postgres through pgvector.

## Decision

Embed with the same model class, `BAAI/bge-small-en-v1.5`, through fastembed, which runs it on the CPU through ONNX. Build the index in memory from the policy leaves when it's first needed: chunks along paragraph breaks, each keeping its leaf and character offsets. Rank by fusing BM25 over words with cosine similarity over the embeddings, by reciprocal rank. Cache the chunk vectors on disk, keyed by a hash of the model and the chunk text.

## Reasons

- **Weight.** sentence-transformers needs PyTorch, about 2 GB installed, on a laptop with 8 GB of memory shared with Spark and the container VM. fastembed and ONNX Runtime add about 100 MB.
- **Same model.** The embeddings are the same BGE model the brief named, so retrieval quality is unchanged.
- **The corpus is small.** Cosine similarity over 700 vectors in memory takes well under a millisecond; a vector index adds a table, a migration, and a sync job for no gain at this size.
- **Exact citation.** Chunks are offsets into the leaf's own text, so a quote is checked against the bytes the proof covers, not against a copy.
- **Questions stay local.** Embedding runs on the machine; no question is sent anywhere to be embedded.

## Alternatives considered

- **sentence-transformers.** The default, rejected for the PyTorch footprint.
- **pgvector.** Kept in the database image for when the corpus grows past what memory holds comfortably.
- **A hosted embedding API.** Rejected: it would send every question to a third party for a step that runs fine locally.

## Consequences

- The first index build embeds every chunk, about a minute; later builds load the cached vectors.
- The model downloads by name on first use and isn't yet pinned to a revision or checked against a hash. It only ranks policy text and never touches a number or a proof.
- If the policy corpus grows to many thousands of sections, moving the vectors into pgvector is the documented next step.
