# 正式设计迁移 · 2026-11-21

> 历史资料说明（2026-11-26补注）：本文保留原日期、基线和当时结论，不代表当前能力或本轮验收；当前入口见[文档中心](README.md)。

## 当前规格与执行计划

采用信息架构方案 A、用户指定完整菜单目录和 Graphite Observatory A 企业观测台。保留全部既有 route name、URL、API 路径、权限语义和业务状态。保留正式迁移资料、页面映射与正式验收截图。

1. 基线：盘点 41 个页面、私有依赖、现有行为测试；368 项前端测试通过。
2. 物理迁移：页面改为 XxxPage，私有代码就近归属；跨域仅共享视口数学和编辑能力读取。更新所有导入与测试，保持断言及发现数量。
3. 导航与设计基础：递归菜单单一真值、身份/面包屑/搜索、标题同步、石墨蓝/冷白令牌和仪器式应用壳。
4. 页面实施：语义资产、本体与图谱、接入抽取、治理、知识库、系统账户认证按独立写入边界分批；保留真实请求及四态。
5. 兼容与验收：旧书签、query/hash、IRI、返回上下文、角色矩阵、异步乱序；定向测试后执行 lint/test/i18n/build/E2E。
6. 浏览器：正式应用各页面家族，双主题/双语、1440/1024/768/375；独立 Quality 审查，按有证据缺陷迭代。

## 边界

不修改后端模型、数据库、权限规则、部署。校验/运行功能仅消费现有真实接口，缺失能力如实记录。真实业务数据不用于破坏性测试。

## 页面映射

所有行兼容方式均为 **原 URL、route name 不变**；变化仅发生在菜单归属、物理源码及正式视觉。菜单归属以新路径首层/子层对应；详情和上下文工具不进入固定菜单。

| route name              | 原文件（views/）                    | 新文件（views/）                                                             | 验证                                     |
| ----------------------- | ----------------------------------- | ---------------------------------------------------------------------------- | ---------------------------------------- |
| `dashboard`             | `Dashboard.vue`                     | `dashboard/DashboardPage.vue`                                                | 结构解析、旧 URL、真实页面家族与已有回归 |
| `knowledge-bases`       | `knowledge/KnowledgeBases.vue`      | `knowledge/KnowledgeBaseListPage.vue`                                        | 结构解析、旧 URL、真实页面家族与已有回归 |
| `knowledge-base-detail` | `knowledge/KnowledgeBaseDetail.vue` | `knowledge/KnowledgeBaseDetailPage.vue`                                      | 结构解析、旧 URL、真实页面家族与已有回归 |
| `knowledge-base-search` | `knowledge/KnowledgeSearch.vue`     | `knowledge/KnowledgeSearchPage.vue`                                          | 结构解析、旧 URL、真实页面家族与已有回归 |
| `ontologies`            | `ontology/Ontologies.vue`           | `ontology/ontologies/OntologiesPage.vue`                                     | 结构解析、旧 URL、真实页面家族与已有回归 |
| `namespaces`            | `ontology/Namespaces.vue`           | `semantic-assets/namespaces/NamespacesPage.vue`                              | 结构解析、旧 URL、真实页面家族与已有回归 |
| `entity-types`          | `ontology/EntityTypes.vue`          | `semantic-assets/entity-types/EntityTypesPage.vue`                           | 结构解析、旧 URL、真实页面家族与已有回归 |
| `entity-detail`         | `ontology/EntityDetail.vue`         | `semantic-assets/entity-types/EntityTypeDetailPage.vue`                      | 结构解析、旧 URL、真实页面家族与已有回归 |
| `relation-types`        | `ontology/RelationTypes.vue`        | `semantic-assets/relation-types/RelationTypesPage.vue`                       | 结构解析、旧 URL、真实页面家族与已有回归 |
| `relation-detail`       | `ontology/RelationDetail.vue`       | `semantic-assets/relation-types/RelationTypeDetailPage.vue`                  | 结构解析、旧 URL、真实页面家族与已有回归 |
| `domains`               | `ontology/Domains.vue`              | `semantic-assets/business-domains/BusinessDomainsPage.vue`                   | 结构解析、旧 URL、真实页面家族与已有回归 |
| `designer`              | `ontology/Designer.vue`             | `ontology/designer/DesignerPage.vue`                                         | 结构解析、旧 URL、真实页面家族与已有回归 |
| `datasources`           | `datasources/DataSources.vue`       | `data-integration/sources/DataSourcesPage.vue`                               | 结构解析、旧 URL、真实页面家族与已有回归 |
| `data-catalog`          | `datasources/DataCatalog.vue`       | `data-integration/catalog/DataCatalogPage.vue`                               | 结构解析、旧 URL、真实页面家族与已有回归 |
| `sample-preview`        | `datasources/SamplePreview.vue`     | `data-integration/catalog/preview/SamplePreviewPage.vue`                     | 结构解析、旧 URL、真实页面家族与已有回归 |
| `mapping-wizard`        | `extraction/MappingWizard.vue`      | `data-integration/mapping/MappingWorkbenchPage.vue`                          | 结构解析、旧 URL、真实页面家族与已有回归 |
| `extraction-runs`       | `extraction/ExtractionRuns.vue`     | `data-integration/runs/ExtractionRunsPage.vue`                               | 结构解析、旧 URL、真实页面家族与已有回归 |
| `extraction-tasks`      | `extraction/ExtractionTasks.vue`    | `data-integration/tasks/ExtractionTasksPage.vue`                             | 结构解析、旧 URL、真实页面家族与已有回归 |
| `ai-assist`             | `extraction/AiAssist.vue`           | `data-integration/mapping/ai-assist/AiAssistPage.vue`                        | 结构解析、旧 URL、真实页面家族与已有回归 |
| `graph-browse`          | `graph/GraphBrowse.vue`             | `graph/browse/GraphBrowsePage.vue`                                           | 结构解析、旧 URL、真实页面家族与已有回归 |
| `graph-entities`        | `graph/GraphEntities.vue`           | `graph/entities/GraphEntitiesPage.vue`                                       | 结构解析、旧 URL、真实页面家族与已有回归 |
| `graph-entity-detail`   | `graph/GraphEntityDetail.vue`       | `graph/entities/GraphEntityDetailPage.vue`                                   | 结构解析、旧 URL、真实页面家族与已有回归 |
| `graph-evidence`        | `graph/GraphEvidence.vue`           | `graph/evidence/GraphEvidencePage.vue`                                       | 结构解析、旧 URL、真实页面家族与已有回归 |
| `graph-reports`         | `graph/GraphReports.vue`            | `ontology/validation/ValidationReportsPage.vue`                              | 结构解析、旧 URL、真实页面家族与已有回归 |
| `governance-rules`      | `governance/GovernanceRules.vue`    | `governance/rules/GovernanceRulesPage.vue`                                   | 结构解析、旧 URL、真实页面家族与已有回归 |
| `governance-clauses`    | `governance/StandardClauses.vue`    | `governance/clauses/StandardClausesPage.vue`                                 | 结构解析、旧 URL、真实页面家族与已有回归 |
| `enum-dictionaries`     | `governance/EnumDictionaries.vue`   | `semantic-assets/configuration/enum-dictionaries/EnumDictionariesPage.vue`   | 结构解析、旧 URL、真实页面家族与已有回归 |
| `assembly-templates`    | `governance/AssemblyTemplates.vue`  | `semantic-assets/configuration/assembly-templates/AssemblyTemplatesPage.vue` | 结构解析、旧 URL、真实页面家族与已有回归 |
| `ontology-export`       | `governance/OntologyExport.vue`     | `governance/exchange/OntologyExchangePage.vue`                               | 结构解析、旧 URL、真实页面家族与已有回归 |
| `account-profile`       | `account/Profile.vue`               | `account/ProfilePage.vue`                                                    | 结构解析、旧 URL、真实页面家族与已有回归 |
| `account-security`      | `account/Security.vue`              | `account/SecurityPage.vue`                                                   | 结构解析、旧 URL、真实页面家族与已有回归 |
| `system-users`          | `system/Users.vue`                  | `system/users/UsersPage.vue`                                                 | 结构解析、旧 URL、真实页面家族与已有回归 |
| `system-roles`          | `system/Roles.vue`                  | `system/roles/RolesPage.vue`                                                 | 结构解析、旧 URL、真实页面家族与已有回归 |
| `system-audit-logs`     | `system/AuditLogs.vue`              | `system/audit-logs/AuditLogsPage.vue`                                        | 结构解析、旧 URL、真实页面家族与已有回归 |
| `system-ai-models`      | `system/AiModels.vue`               | `system/ai-models/AiModelsPage.vue`                                          | 结构解析、旧 URL、真实页面家族与已有回归 |
| `forbidden`             | `Forbidden.vue`                     | `errors/ForbiddenPage.vue`                                                   | 结构解析、旧 URL、真实页面家族与已有回归 |
| `not-found`             | `NotFound.vue`                      | `errors/NotFoundPage.vue`                                                    | 结构解析、旧 URL、真实页面家族与已有回归 |
| `login`                 | `auth/Login.vue`                    | `auth/LoginPage.vue`                                                         | 结构解析、旧 URL、真实页面家族与已有回归 |
| `register`              | `auth/Register.vue`                 | `auth/RegisterPage.vue`                                                      | 结构解析、旧 URL、真实页面家族与已有回归 |
| `forgot-password`       | `auth/ForgotPassword.vue`           | `auth/ForgotPasswordPage.vue`                                                | 结构解析、旧 URL、真实页面家族与已有回归 |
| `reset-password`        | `auth/ResetPassword.vue`            | `auth/ResetPasswordPage.vue`                                                 | 结构解析、旧 URL、真实页面家族与已有回归 |

完整私有文件映射见 `frontend-migration-map-2026-11-21.json`。跨域回归测试归入 `web/src/__tests__`，测试运行器归入 `web/src/testing`；单域测试跟随页面。

## 实施状态

以下为 2026-11-21 的正式迁移验收记录：

- 结构：41 个页面级 route name 全部解析到新 `XxxPage.vue`；菜单叶子、权限身份、详情归属和搜索索引共用 `web/src/layout/navigation/` 单一真值。
- 前端门禁：`make test` 通过前端 382 项、后端 1757 项；`make lint`、`pnpm -C web typecheck`、`pnpm -C web build` 通过；i18n key 检查通过，中英文各 2114 键。Naive UI 仍有 >500 kB chunk 警告，不影响构建成功。
- 全量 Playwright：最终代码版本运行 255 项，253/255 一次通过；两项仅属于同一实体创建并发测试，隔离复跑 2/2 通过。分层套件另通过导航 22/22、图形/证据/权限定向 29/29、截图 1/1、AI 1/1、建模 2/2、治理 5/5。
- 截图完整性：历史验收记录中，21 张正式截图曾重新计算校验并全部通过；截图与校验清单已从当前文档树清理。Git 来源及取回方法见[文档盘点](maintenance/document-inventory.md)。
- 导航 E2E：`pnpm exec playwright test e2e/navigation-migration.spec.ts` 通过 22/22，覆盖 ADMIN / EDITOR / VIEWER、三级菜单、隐藏工具归属、对象面包屑、旧 URL 与 query/hash/IRI、回退与前进、双主题和 1440/1024/768/375 屏幕。

正式页面的事实边界仍按本文件前文：接口未提供的能力不被伪造；页面覆盖与验收以正式实现、真实 API 及相应验证为依据。

## 独立原型清理验证 · 2026-11-23

- 承接核对：独立前端源码复核确认选定的 A 设计及 18 个业务屏幕均有正式承接；41 个正式页面导入目标均存在。模拟连接验证、方向选择与强制状态切换等原型演示工具随原型清理。
- 清理范围：删除 56 个仓库原型文件和 77 个本地原型证据文件，覆盖源码、入口、模拟数据、词典、专用检查脚本、设计评审说明与截图；移除原型专用 ESLint 例外。原型资料在删除前已另行完整备份。
- 已验证：`make lint` 通过；`make test` 通过前端 382 项、后端 1757 项（pytest 报告 60 条警告）；i18n 检查通过，中英文各 2114 键。
- 构建一致：清理前后两次正式 Vite 构建成功，87 项 manifest 均无原型入口；130 个输出文件的 SHA-256 全部一致，无新增、删除或内容差异。
- 正式资料：保留正式迁移记录、页面映射与 21 张正式验收截图，截图校验全部通过。
- 未验证：本轮未重跑浏览器 E2E 或像素对照；前文的 E2E 结果属于 2026-11-21 的验收记录。
