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

管理员在「系统管理 → AI 模型」中新增、查询、编辑和删除 OpenAI 兼容服务配置（`/system/ai-models`）：

- 为对话（CHAT）与向量（EMBEDDING）分别填写名称、Base URL、模型名、版本、超时和 API Key，启用后显式选择该能力的默认模型。保存和选择默认模型不会主动调用服务。
- API Key 由后端加密保存，列表与详情仅显示是否已配置。编辑时留空保留原密钥；替换或清除需要明确操作。更换服务地址的 origin 必须同时替换或清除密钥。请保持服务端 `KG_CRYPTO_KEY` 稳定，并妥善管理数据库及加密密钥的备份。
- Base URL 是协议前缀，客户端追加 `chat/completions` 或 `embeddings`。更换 embedding 模型/部署时更新模型版本并重新处理文档，旧向量会标为过期。处理中配置发生变化会终止本次索引发布，保留上一成功索引。
- 禁用或删除默认模型会清除对应默认选择；未选择可用默认模型时仍可上传和关键词检索，其他能力明确禁用。运行时不再读取旧的 `KG_LLM_*` / `KG_EMBEDDING_*` 环境变量来选择服务；既有部署需在管理界面重新录入配置。
- `KG_KNOWLEDGE_WORKERS_ENABLED` 默认 `true`；进程生命周期管理持久化队列，失败重处理保留旧活动索引。文档和历史索引保留，归档不释放文档额度，尚无物理删除或历史清理策略。

已有数据库需在备份并确认目标库后，于 `server/` 执行 `.venv/bin/alembic upgrade head`。`0020_knowledge_bases` 创建知识库表，`0021_ai_model_configs` 新增模型配置和两类默认选择，初始默认均为空。降级到 `0020_knowledge_bases` 会删除模型配置；降级到 `0019_asset_audit` 还会删除知识库数据，必须先备份。生产环境使用迁移，不以启动时自动建表代替迁移。

本地 SQLite、浏览器和本地模型协议夹具已验证；真实 AI 效果、生产 PostgreSQL 与并发容量仍需环境验收。2026-11-19 在本机对 1 万片段 / 384 维合成样本做三次精确语义检索，中位约 4.97 秒、最大约 6.75 秒；不含模型网络请求，也不代表生产延迟承诺。协议回归运行 `make test-e2e-ai`，不调用真实模型。

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
