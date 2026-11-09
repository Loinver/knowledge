# 知识中台 · Knowledge Platform

本体建模 → 数据接入 → 映射配置 → 抽取执行 → 图谱与证据追溯，端到端闭环的企业语义建模与知识抽取平台。
默认中文，支持英文；MIT 协议；可自托管。

English: see below / [README.en.md](./README.en.md)

## 它解决什么

- **语义资产可复用**：实体类型 / 关系类型 / 业务域 / 本体，各自版本化、可发布、可冻结，上游改版不会静默影响下游。
- **从真实数据到图谱**：接一个只读库，配置映射，跑抽取，产出带证据的图谱版本。
- **结论可信**：校验只有「通过 / 违反 / 不适用 / 未执行」四态，未执行绝不显示为通过；每条事实都能反查到来源表、行键、字段与运行批次。

规范依据：GB/T 48000.3—2026《标准数字化 第 3 部分：本体建模要求》（仓库内只保留条款编号与自撰描述，不收录标准正文）。

## 技术栈

| 层       | 选型                                                                          |
| -------- | ----------------------------------------------------------------------------- |
| 前端     | Vue 3 + TypeScript + Vite                                                     |
| 后端     | Python 3.12 + FastAPI                                                         |
| 元数据库 | PostgreSQL（开发可用 SQLite）                                                 |
| 语义     | rdflib（RDF/SPARQL）+ pySHACL（真实 SHACL 校验）+ owlrl（推理最小集），可替换 |
| 图谱存储 | 关系表三元组（规模上量后再评估图库）                                          |

## 快速开始

```bash
make install     # 安装依赖与 git hooks
make dev         # 前后端一体启动（后端 :4000，前端 :4010 代理 /api）
make start       # 构建前端 + 单端口启动（:4000 同时提供页面与 API）
make lint        # 全量代码校验（ESLint + Prettier + vue-tsc + Ruff + Mypy + 架构边界测试）
make test        # 前端 + 后端测试
make test-e2e    # Playwright 8 步主流程与页面响应式验收
pnpm run commit  # 交互式提交（Conventional Commits）
```

贡献前请先读 [CONTRIBUTING.md](./CONTRIBUTING.md)。

## 知识库 MVP

导航中的「知识库」支持创建、上传 UTF-8 TXT / Markdown / CSV、查看处理任务、关键词检索、原文定位和可恢复归档。所有登录用户可读，ADMIN / EDITOR 可维护，沿用全局权限；尚无逐库 ACL。单文件最多 2 MiB，每库最多 100 份文档（含归档）、10,000 个活动片段，每文档最多 2,000 个片段。PDF / Word / OCR 未支持。

语义与混合检索使用 SQL 中保存的 embedding 做有界精确余弦检索；混合排序为 BM25 + RRF。证据摘录问答只返回本次检索证据中的原文引用。图谱人工关联固定结果集和事实版本，不会自动创建事实，也不冒充已有抽取证据。

在后端环境变量或 `server/.env` 配置兼容模型服务；密钥不得提交或放入前端：

- 对话：`KG_LLM_BASE_URL`、`KG_LLM_API_KEY`、`KG_LLM_MODEL`、`KG_LLM_TIMEOUT_SECONDS`。
- Embedding：`KG_EMBEDDING_BASE_URL`、`KG_EMBEDDING_API_KEY`、`KG_EMBEDDING_MODEL`、`KG_EMBEDDING_VERSION`、`KG_EMBEDDING_TIMEOUT_SECONDS`。
- Base URL 是协议前缀，客户端追加 `chat/completions` 或 `embeddings`。更换 embedding 模型/部署时递增版本并重新处理文档，旧向量会标为过期。未配置时仍可上传和关键词检索，其他能力明确禁用。
- `KG_KNOWLEDGE_WORKERS_ENABLED` 默认 `true`；进程生命周期管理持久化队列，失败重处理保留旧活动索引。文档和历史索引保留，归档不释放文档额度，尚无物理删除或历史清理策略。

已有数据库需在备份并确认目标库后，于 `server/` 执行 `.venv/bin/alembic upgrade head`，新增迁移为 `0020_knowledge_bases`。降级到 `0019_asset_audit` 会删除全部新知识库表和数据，必须先备份；代码回退可以保留这些表。不要在生产环境使用启动时自动建表代替迁移。

本地 SQLite、浏览器和本地模型协议夹具已验证；真实 AI 效果、生产 PostgreSQL 与并发容量仍需环境验收。1 万片段 / 384 维的本地合成样本精确语义检索中位约 5.35 秒，不代表生产延迟承诺。协议回归运行 `pnpm exec playwright test --config e2e/knowledge-ai.config.ts`，不调用真实模型。

## 目录

```
web/      前端（Vue 3 + Vite）
server/   后端（FastAPI + Ruff/Mypy/Pytest）
samples/  只读样例源库与 seed（M2 交付）
docs/     开发计划与架构决策记录（ADR）
```

仓库根只放治理文件（LICENSE / README / CI / hooks / 工具链配置），业务代码一律在 `web/` 与 `server/` 内。
开发计划见 [docs/development-plan.zh-CN.md](./docs/development-plan.zh-CN.md)，后端选型理由见 [docs/adr/0001-backend-stack.md](./docs/adr/0001-backend-stack.md)。

## 路线图

M0 基座与语义引擎 → M1 语义资产闭环 → M2 数据接入与映射 → **M3 抽取与图谱闭环（v0.1.0，主流程贯通）** → M4 规范符合性（v1.0.0）→ M5 规模化。

M4 正在开发：规则资产管理、真实 SHACL 正反例检查及已发布本体 RDF 导出已进入验证。完整范围、剩余工作及当前限制见 [M4 开发进度](./docs/m4-progress.zh-CN.md)。

---

## English

An end-to-end platform for enterprise semantic modeling and knowledge extraction:
ontology modeling → data onboarding → mapping → extraction → graph with evidence tracing.

- Versioned semantic assets (entity/relation/domain/ontology) with publish-time freezing.
- Real read-only sources, real SHACL validation, four-state validation results (pass / violation / not-applicable / not-run).
- Every fact is traceable back to source table, row key, column and run batch.
- Chinese by default, English supported. Licensed under MIT.

See [CONTRIBUTING.md](./CONTRIBUTING.md) before opening a PR.
