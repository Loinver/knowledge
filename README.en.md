# Knowledge Platform

An end-to-end platform for enterprise semantic modeling and knowledge extraction:
ontology modeling → data onboarding → mapping configuration → extraction → graph with evidence tracing.

Chinese by default, English supported. MIT licensed. Self-hostable.

## Why it exists

- **Reusable semantic assets**: entity types, relation types, business domains and ontologies are versioned, publishable and frozen at publish time — upstream revisions never silently change published downstream artifacts.
- **From real data to a real graph**: connect a read-only source, configure mappings, run extraction, get a graph version with evidence.
- **Honest validation**: results are always one of four states — pass / violation / not-applicable / **not-run**. A check that never ran is never reported as passing.
- **Traceable facts**: every triple can be traced back to source connection, table, row key, column and run batch.

Reference specification: GB/T 48000.3—2026 (only clause numbers and short original descriptions are kept in this repo; the standard's text is not redistributed).

## Stack

| Layer          | Choice                                                                                       |
| -------------- | -------------------------------------------------------------------------------------------- |
| Frontend       | Vue 3 + TypeScript + Vite                                                                    |
| Backend        | Python 3.12 + FastAPI                                                                        |
| Metadata store | PostgreSQL (SQLite for development)                                                          |
| Semantics      | rdflib (RDF/SPARQL) + pySHACL (real SHACL validation) + owlrl (minimal reasoning), pluggable |
| Graph storage  | relational triple tables (a graph database is reconsidered only at scale)                    |

## Getting started

```bash
make install     # install dependencies and git hooks
make dev         # run frontend and backend together
make lint        # ESLint + Prettier + vue-tsc + Ruff + Mypy + architecture boundary tests
make test        # frontend and backend tests
make test-e2e    # Playwright main-flow and responsive UI checks
pnpm run commit  # interactive commit (Conventional Commits)
```

Read [CONTRIBUTING.md](./CONTRIBUTING.md) before opening a PR. Design docs live in [docs/](./docs/).

## Knowledge-base MVP

The Knowledge bases navigation entry supports creation, UTF-8 TXT / Markdown / CSV uploads, processing tasks, keyword search, original evidence, and reversible archiving. All authenticated users can read; ADMIN / EDITOR can maintain content under the existing global roles. Per-base ACLs are not implemented. Limits are 2 MiB per file, 100 documents per base including archived documents, 10,000 active chunks per base, and 2,000 chunks per document. PDF, Word and OCR are unsupported.

Semantic search uses bounded exact cosine scoring over embeddings stored in SQL. Hybrid search combines BM25 and semantic ranks with RRF. Extractive answers return only exact quotations from retrieved evidence. Manual graph links pin existing graph/fact versions; they do not create facts or represent extraction provenance.

Administrators create, browse, edit and delete OpenAI-compatible services under System management → AI models (`/system/ai-models`):

- Configure a name, base URL, model name, version, timeout and API key for each CHAT or EMBEDDING service. Enable it and explicitly select the default for its capability. Saving or selecting a default does not call the service.
- Keys are encrypted on the server; list and detail responses only indicate whether a key is present. Leaving the key blank when editing preserves it; replacement and clearing are explicit actions. Changing the URL origin requires replacing or clearing the key. Keep the server's `KG_CRYPTO_KEY` stable and manage database and encryption-key backups securely.
- The client appends `chat/completions` or `embeddings` to the protocol base URL. Update the embedding model version when replacing a deployment/model and reprocess documents. Old vectors are marked stale. Configuration changes during processing abort publication of the new index and preserve the previous successful index.
- Disabling or deleting a default model clears that selection. Without an available default, uploads and keyword search remain available; other capabilities explicitly show as unavailable. Runtime selection no longer uses legacy `KG_LLM_*` / `KG_EMBEDDING_*` environment variables; existing deployments must enter their settings in the management page.
- `KG_KNOWLEDGE_WORKERS_ENABLED` defaults to `true`. Workers follow application lifespan and process a durable queue. Failed reprocessing preserves the previous active index. Archived documents and historical indexes remain stored; no physical deletion or retention cleanup is implemented.

For an existing database, back it up and confirm the target before running `.venv/bin/alembic upgrade head` from `server/`. `0020_knowledge_bases` adds the knowledge tables; `0021_ai_model_configs` adds model configurations and two initially empty default selections. Downgrading to `0020_knowledge_bases` deletes model configurations; downgrading to `0019_asset_audit` also deletes knowledge data. Back up before downgrading. Production must use migrations instead of startup table creation.

Local SQLite, browser flows and an isolated model protocol fixture are verified. Real model quality, production PostgreSQL and concurrent capacity still require environment validation. Three local exact semantic searches over a synthetic 10,000-chunk / 384-dimensional corpus on November 19, 2026 had a median of about 4.97 seconds and a maximum of 6.75 seconds. These exclude model network requests and are not a production latency guarantee. Run `make test-e2e-ai` for the local protocol fixture, without calling a real provider.

## Layout

```
web/       frontend (Vue 3)
server/    backend (FastAPI)
samples/   read-only sample source database (M2)
docs/      design docs and ADRs
```

## Roadmap

M0 foundation and semantic engine → M1 semantic assets → M2 data onboarding and mapping → **M3 extraction and graph loop (v0.1.0, end-to-end)** → M4 specification conformance (v1.0.0) → M5 scale.

M4 is in development: rule management, real SHACL example checks, and published ontology RDF exports are under validation. See [M4 progress (Chinese)](./docs/m4-progress.zh-CN.md) for the full scope, remaining work, and current limitations.
