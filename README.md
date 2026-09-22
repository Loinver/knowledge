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
make dev         # 前后端一体启动（后端 :8000，前端 :5173 代理 /api）
make start       # 构建前端 + 单端口启动（:8000 同时提供页面与 API）
make lint        # 全量代码校验（ESLint + Prettier + vue-tsc + Ruff + Mypy）
make test        # 后端测试
npm run commit   # 交互式提交（Conventional Commits）
```

贡献前请先读 [CONTRIBUTING.md](./CONTRIBUTING.md)。

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
