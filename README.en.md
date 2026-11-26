# Knowledge Platform

A self-hosted workspace for enterprise semantic modeling, read-only data extraction, graph exploration and evidence tracing. A parallel document knowledge base supports retrieval, source excerpts and extractive answers.

Chinese is the default UI language; English is supported. MIT licensed. Suitable for business pilots and integration evaluation; production capacity and operational readiness require deployment-specific acceptance.

[中文](README.md) · [Documentation](docs/README.md) · [Feature catalog](docs/product/feature-catalog.md) · [Getting started](docs/user-guide/quickstart.md)

Reviewed on 2026-11-26 against `9222236` plus the uncommitted A-style UI workspace. This is not a released version. See the [verification record](docs/maintenance/verification-2026-11-26.md).

## Capabilities and workflow

**Semantic assets → published ontology → data onboarding → published mappings → extraction → graph exploration → evidence tracing.**

- Reusable entity/relation types, domains, enumerations and assembly templates; publication pins upstream versions.
- Read-only source discovery, metadata snapshots, mapping configuration, sample compilation and extraction histories.
- Graph facts, source rows, fields, runs and frozen mapping versions; manually linked documents are supplementary evidence, not extraction provenance.
- UTF-8 TXT/Markdown/CSV knowledge bases, keyword/semantic/hybrid search and evidence-based extractive answers. Keyword search works without a model; other capabilities require available default model services.
- Governance rules and four-state validation: PASS, VIOLATION, NA and NOT_RUN. A check that did not run is never a pass.
- Global ADMIN/EDITOR/VIEWER roles, account management, business audit records and model configuration.

See the [product overview](docs/product/overview.md), [module guides](docs/README.md) and [limitations](docs/product/limitations.md). Detailed guides currently use Chinese.

## Run locally

Requirements: Node.js ≥22.18.0, pnpm 11.7.0, Python ≥3.12. Installation requires network access. From the repository root:

```sh
make install
make seed-admin
make dev
```

Open `http://127.0.0.1:4010/`; the API runs on port 4000. `make seed-admin` creates the first administrator only in an empty account store. Its default username is `admin`, with a randomly generated password displayed once. **There is no universal default password.** The command refuses an existing account store and is not a password reset tool. Public registration is disabled by default.

The default development metadata database is `server/knowledge.db`. Configuration is read relative to the backend process working directory; these Make targets run it from `server/`. Initialization, migration and startup must use the same database configuration.

`make start` builds the frontend and serves UI/API on `0.0.0.0:4000`. It does not automatically enable production mode. Production needs PostgreSQL, a protected independent encryption key, migrations, HTTPS/process management and environment validation. See [deployment](docs/operations/deployment.md) and [configuration](docs/operations/configuration.md).

## Environments and boundaries

- Development, preview and E2E use separate databases and credentials. Default E2E uses temporary data and ports 5199/8123. Isolated prototypes are not business features.
- No per-base ACL, multi-tenancy, SSO, MFA, billing or SLA commitment. Rule-to-standard references do not constitute certification.
- PDF, Word and OCR are unsupported. Model quality and external service compatibility have not been verified in this review.
- PostgreSQL/MySQL source connectors exist, but their required drivers are not fully declared in the default installation. The `production` pg8000 dependency serves the metadata database, not these source connectors.
- Incremental extraction is restricted to supported immutable append-only integer-key/watermark scenarios; it is not general CDC. Extraction scheduling runs in-process.
- Production PostgreSQL, high availability, backup recovery and capacity remain deployment acceptance work.

## Architecture

Vue 3, TypeScript, Vite, Pinia and vue-i18n on the frontend; FastAPI, SQLAlchemy and Alembic on the backend. SQLite is the development store; production configuration requires PostgreSQL. rdflib, pySHACL and owlrl provide semantic adapters; graph facts are stored in relational tables.

```text
web/       Application UI and frontend tests
server/    APIs, domain services, models, migrations and backend tests
samples/   Fictional source database and seed SQL
scripts/   Initialization, schema generation and checks
docs/      Product, user, operations, development and historical records
.agents/   Engineering conventions and completion checks
```

Runtime `/openapi.json` and `/docs` describe the API. Generated frontend types are checked with `make check-api`; a drift check does not prove backward compatibility.

## Common commands

| Command                                                                    | Purpose                                          |
| -------------------------------------------------------------------------- | ------------------------------------------------ |
| `make dev` / `make start`                                                  | Development / built single-port service          |
| `make seed-admin`                                                          | First administrator initialization               |
| `make lint` / `make test`                                                  | Static checks / frontend and backend tests       |
| `make test-e2e`                                                            | Isolated browser suite                           |
| `make test-e2e-ai` / `make test-e2e-modeling` / `make test-e2e-governance` | Protocol-fixture, modeling and governance suites |
| `make check-api`                                                           | Generated API type drift                         |
| `pnpm run check:docs` / `pnpm run check:docs:staged`                       | Documentation structure / staged impact report   |
| `pnpm run commit`                                                          | Interactive git-cz commit                        |

Install the browser before first use: `pnpm exec playwright install chromium`. Local model protocol fixtures do not establish real model quality.

## Documentation and contribution

Start with the [documentation hub](docs/README.md), [architecture guide](docs/development/architecture.md), [troubleshooting](docs/operations/troubleshooting.md) and [CONTRIBUTING](CONTRIBUTING.md). Historical milestones retain their original dates and are indexed in the [document inventory](docs/maintenance/document-inventory.md).

Changes to features, permissions, states, workflows or configuration must assess and update related documents under the [single documentation policy](.agents/conventions/documentation.md). A concrete explanation is required when no documentation update is needed; editing an unrelated Markdown file is not sufficient.
