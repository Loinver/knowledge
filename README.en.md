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
make lint        # ESLint + Prettier + vue-tsc + Ruff + Mypy
make test        # backend tests
npm run commit   # interactive commit (Conventional Commits)
```

Read [CONTRIBUTING.md](./CONTRIBUTING.md) before opening a PR. Design docs live in [docs/](./docs/).

## Layout

```
web/       frontend (Vue 3)
server/    backend (FastAPI)
samples/   read-only sample source database (M2)
docs/      design docs and ADRs
```

## Roadmap

M0 foundation and semantic engine → M1 semantic assets → M2 data onboarding and mapping → **M3 extraction and graph loop (v0.1.0, end-to-end)** → M4 specification conformance (v1.0.0) → M5 scale.
