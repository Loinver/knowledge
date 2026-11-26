# 知识中台 · Knowledge Platform

面向企业语义建模、数据抽取与证据追溯的自托管知识工作平台。通过可复用语义资产和版本化本体，把只读业务数据转为图谱；通过文档知识库提供检索、原文定位和证据摘录问答。

默认中文，支持英文界面，项目采用 MIT 许可。当前定位是可开展业务试点和集成评估的应用；生产容量、外部系统兼容与运维保障需针对部署环境验收。

[文档中心](docs/README.md) · [功能台账](docs/product/feature-catalog.md) · [快速入门](docs/user-guide/quickstart.md) · [English](README.en.md)

> 内容核验于2026-11-26，基于 `9222236` 加当前未提交的 A 风格界面工作区，非已发布版本。实现状态与验证状态见[核验记录](docs/maintenance/verification-2026-11-26.md)。

## 核心能力

| 能力           | 业务用途                                               | 详细说明                                             |
| -------------- | ------------------------------------------------------ | ---------------------------------------------------- |
| 语义资产与本体 | 统一业务概念，维护类型、关系、域、枚举、模板和版本     | [建模与治理](docs/user-guide/modeling-governance.md) |
| 数据接入与映射 | 检查源结构，配置字段、关系、业务键及冻结的目标版本     | [数据到图谱](docs/user-guide/data-graph.md)          |
| 抽取与运行     | 执行任务，查看状态、异常、隔离数据和历史结果集         | [数据功能台账](docs/product/features-data-graph.md)  |
| 图谱与证据     | 探索实体及关系，追溯来源表、行键、字段和运行           | [图谱操作](docs/user-guide/data-graph.md)            |
| 文档知识库     | 处理TXT/Markdown/CSV，关键词、语义与混合检索，引用原文 | [知识库与系统](docs/user-guide/knowledge-system.md)  |
| 治理与管理     | 四态校验、规则条款、业务审计、用户角色和模型配置       | [权限说明](docs/user-guide/roles-permissions.md)     |

业务主线：**语义资产 → 本体建模与发布 → 数据接入 → 映射配置与发布 → 抽取执行 → 图谱探索与证据追溯**。文档知识库是并行知识来源，人工关联已有图事实不等于自动抽取来源证据。

## 快速启动

要求 Node.js ≥22.18.0、pnpm 11.7.0、Python ≥3.12。首次安装需要网络；从仓库根目录执行：

```sh
make install
make seed-admin
make dev
```

`make seed-admin` 仅在账号库为空时创建首个管理员，默认用户名 `admin`，随机密码只在终端显示一次。**没有通用默认密码**；已有账号时该命令拒绝再次创建，不用于重置密码。公开注册默认关闭，后续用户由管理员发放。

打开 `http://127.0.0.1:4010/`，后端默认 `http://127.0.0.1:4000`。开发元数据库默认位于 `server/knowledge.db`，`.env` 读取位置随后端进程工作目录而定。详见[安装与部署](docs/operations/deployment.md)。

单端口构建启动使用 `make start`，在4000端口提供页面与API，默认绑定所有网卡。生产环境还需 PostgreSQL、独立密钥、迁移、反向代理与运维验收，不能只执行该命令就视为完成生产部署。

## 环境与能力边界

- **开发、预览、测试账号不通用**：隔离预览连接独立数据库；E2E使用临时数据库和专用端口，不操作开发库。设计原型不作为正式业务入口。
- **版本与状态真实**：已发布本体固定成员资源版本，已发布映射固定本体版本；校验严格区分PASS、VIOLATION、NA、NOT_RUN。冻结不代表上游自动升级。
- **权限范围**：ADMIN、EDITOR、VIEWER全局角色；没有多租户或逐知识库ACL，不承诺SSO、MFA、计费与SLA。
- **知识库范围**：UTF-8 TXT/Markdown/CSV；不支持PDF、Word或OCR。模型能力需管理员配置可用的CHAT/EMBEDDING默认服务。关键词检索不要求模型。
- **连接范围**：SQLite源可用于本地验证；PostgreSQL/MySQL源连接器实现存在，但默认安装不包含全部所需源驱动，目标环境需验证。元数据库驱动与源库驱动不同。
- **商业采用**：标准条款关联和校验报告不等于第三方认证。容量、生产PostgreSQL、真实模型效果与高可用尚不能作为承诺，见[限制清单](docs/product/limitations.md)。

## 架构与目录

Vue 3 + TypeScript + Vite前端，FastAPI + SQLAlchemy后端；开发SQLite、生产配置要求PostgreSQL；语义适配使用rdflib、pySHACL及owlrl。图谱数据保存在关系表中，后台知识处理由应用生命周期管理。

```text
web/       正式前端与页面测试
server/    API、领域服务、数据模型、迁移与测试
samples/   虚构样例源库与SQL种子
scripts/   初始化、契约生成和检查工具
docs/      产品、用户、运维、开发文档及历史决策
.agents/   项目规范与完工自检
```

架构与契约见[开发指南](docs/development/architecture.md)。接口以运行服务 `/openapi.json`、`/docs` 为准，前端生成类型通过 `make check-api` 校验漂移。

## 常用命令

| 命令                                                                       | 用途                             |
| -------------------------------------------------------------------------- | -------------------------------- |
| `make dev` / `make start`                                                  | 开发双端口 / 构建后单端口启动    |
| `make seed-admin`                                                          | 空账号库初始化，生成独立口令     |
| `make lint` / `make test`                                                  | 静态检查 / 前后端测试            |
| `make test-e2e`                                                            | 隔离浏览器主套件                 |
| `make test-e2e-ai` / `make test-e2e-modeling` / `make test-e2e-governance` | 模型协议、本体建模与治理专项     |
| `make check-api`                                                           | OpenAPI类型漂移检查              |
| `pnpm run check:docs`                                                      | 文档链接、功能登记和入口覆盖检查 |
| `pnpm run check:docs:staged`                                               | 暂存变更的文档影响检查           |
| `pnpm run commit`                                                          | git-cz交互式提交                 |

首次运行浏览器测试需安装Chromium：`pnpm exec playwright install chromium`。真实模型协议与业务效果分别验收；本地模型夹具不能代表真实服务。

## 文档与贡献

- 产品评估：[介绍](docs/product/overview.md)、[术语](docs/product/glossary.md)、[全功能台账](docs/product/feature-catalog.md)、[限制](docs/product/limitations.md)。
- 使用操作：[快速入门](docs/user-guide/quickstart.md)、[工作台](docs/user-guide/workbench.md)、[模块指南](docs/README.md)。
- 实施运维：[部署](docs/operations/deployment.md)、[配置](docs/operations/configuration.md)、[故障排查](docs/operations/troubleshooting.md)。
- 开发维护：[贡献指南](CONTRIBUTING.md)、[架构](docs/development/architecture.md)、[文档同步规则](.agents/conventions/documentation.md)。
- 历史资料：[盘点与归档索引](docs/maintenance/document-inventory.md)。历史里程碑不是当前发布或认证声明。

功能、权限、状态、配置或流程变化时，必须评估并同步对应功能台账、指南和验证说明。无需文档更新时给出具体依据，不能仅修改无关Markdown来通过检查。
