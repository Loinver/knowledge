# 知识库、账户与系统管理功能台账

核验日期：2026-11-26；基于 `9222236` 加未提交工作区，非发布版本。所有功能均追踪真实实现；未宣称本轮全部验收。操作见[知识库与系统指南](../user-guide/knowledge-system.md)，权限见[角色说明](../user-guide/roles-permissions.md)，执行范围见[核验记录](../maintenance/verification-2026-11-26.md)。

## 索引

| 编号                | 功能                           | 入口                                       |
| ------------------- | ------------------------------ | ------------------------------------------ |
| [KNO-001](#kno-001) | 知识库目录与生命周期           | `/knowledge-bases`、`/knowledge-bases/:id` |
| [KNO-002](#kno-002) | 文档上传、原文与归档管理       | `/knowledge-bases/:id`                     |
| [KNO-003](#kno-003) | 持久化处理任务与索引代际       | 所属工作区/API/后台                        |
| [KNO-004](#kno-004) | 关键词、语义与混合检索         | `/knowledge-bases/:id/search`              |
| [KNO-005](#kno-005) | 基于引用的证据摘录问答         | `/knowledge-bases/:id/search`              |
| [KNO-006](#kno-006) | 片段原文定位与人工图事实关联   | 所属工作区/API/后台                        |
| [ACC-001](#acc-001) | 首个管理员、登录会话与可选注册 | `/login`、`/register`                      |
| [ACC-002](#acc-002) | 个人资料与账号改密             | `/account/profile`、`/account/security`    |
| [ACC-003](#acc-003) | 受控密码找回与一次性重置       | `/forgot-password`、`/reset-password`      |
| [SYS-001](#sys-001) | 管理员用户管理                 | `/system/users`                            |
| [SYS-002](#sys-002) | 固定角色及成员数查看           | `/system/roles`                            |
| [SYS-003](#sys-003) | AI服务配置与默认能力           | `/system/ai-models`                        |
| [SYS-004](#sys-004) | 账号审计与业务资产审计         | `/system/audit-logs`                       |

<a id="kno-001"></a>

## KNO-001 知识库目录与生命周期

**目标与价值**：统一管理一组文档及其检索上下文，减少散落的制度/业务说明。

**角色、前提与权限**：所有登录用户读取，EDITOR/ADMIN创建和维护；全局共享，不是个人私有库。

**操作、输入输出与状态**：按名称/状态搜索、排序分页；创建和编辑名称描述；以If-Match修订归档/恢复。返回库详情、统计和新修订；归档影响后续检索和写入。

**实现状态与限制**：已有实现；无逐库ACL；归档不是物理删除；恢复不自动把所有此前单独归档文档恢复。

**验证状态**：本轮浏览器建库、查看、归档恢复相关流程通过；所有过滤与并发组合未逐项实测。

**源码**：[web/src/views/knowledge/KnowledgeBaseListPage.vue](../../web/src/views/knowledge/KnowledgeBaseListPage.vue)；[web/src/views/knowledge/KnowledgeBaseDetailPage.vue](../../web/src/views/knowledge/KnowledgeBaseDetailPage.vue)；[server/app/api/v1/knowledge.py](../../server/app/api/v1/knowledge.py)；[server/app/domain/knowledge_service.py](../../server/app/domain/knowledge_service.py)；[server/app/models/knowledge.py](../../server/app/models/knowledge.py)。

**测试位置**：[server/tests/test_knowledge_service.py](../../server/tests/test_knowledge_service.py)；[e2e/knowledge-base.spec.ts](../../e2e/knowledge-base.spec.ts)。

**用户文档**：[操作与失败处理](../user-guide/knowledge-system.md#kno)、[权限](../user-guide/roles-permissions.md)。

<a id="kno-002"></a>

## KNO-002 文档上传、原文与归档管理

**目标与价值**：把可读取的原文纳入可追溯知识索引，保留来源与历史。

**角色、前提与权限**：EDITOR/ADMIN上传/归档/恢复；登录用户可看详情/原文；需要可写知识库。

**操作、输入输出与状态**：上传原始文件字节与文件名；返回文档及处理任务；同库相同字节哈希返回已有文档并标记重复。文档详情含解析/索引/任务状态；归档和恢复校验修订。

**实现状态与限制**：已有实现；仅UTF-8 TXT/Markdown/CSV，2MiB/文件、100文档/库（含归档）；无PDF/Word/OCR、原文在线覆盖编辑或物理删除。归档不是保密或销毁，原文/历史证据仍可按允许入口读取。

**验证状态**：本轮浏览器上传、原文证据、VIEWER限制及归档恢复通过；全部文件错误组合未重跑。

**源码**：[web/src/views/knowledge/components/DocumentDrawer.vue](../../web/src/views/knowledge/components/DocumentDrawer.vue)；[server/app/domain/knowledge_parser.py](../../server/app/domain/knowledge_parser.py)；[server/app/domain/knowledge_service.py](../../server/app/domain/knowledge_service.py)；[server/app/api/v1/knowledge.py](../../server/app/api/v1/knowledge.py)；[server/app/api/v1/knowledge_retrieval.py](../../server/app/api/v1/knowledge_retrieval.py)。

**测试位置**：[server/tests/test_knowledge_parser.py](../../server/tests/test_knowledge_parser.py)；[server/tests/test_knowledge_service.py](../../server/tests/test_knowledge_service.py)；[e2e/knowledge-base.spec.ts](../../e2e/knowledge-base.spec.ts)。

**用户文档**：[操作与失败处理](../user-guide/knowledge-system.md#kno)、[权限](../user-guide/roles-permissions.md)。

<a id="kno-003"></a>

## KNO-003 持久化处理任务与索引代际

**目标与价值**：可靠区分待处理、解析结果和当前可查询索引，避免失败覆盖旧成果。

**角色、前提与权限**：上传/重处理需EDITOR/ADMIN；应用knowledge worker开启；所有登录用户可读任务。

**操作、输入输出与状态**：上传入队或手工重处理；QUEUED→RUNNING→SUCCESS/PARTIAL/FAILED/CANCELLED/INTERRUPTED；阶段QUEUED/EXTRACTING/INDEXING/FINISHED。任务租约/心跳和归属检查；成功发布新active_generation，失败保留旧活动索引。

**实现状态与限制**：已有实现；最多2000片段/文档、10000活动片段/库；部分CSV可保留有效前段并报PARTIAL。无配置向量模型仍可建关键词索引；索引历史保留，无自动物理清理。不等同抽取任务的进程内调度实现。

**验证状态**：源码确认；本轮上传后的处理完成已观察，租约中断及全部发布竞争未重跑。

**源码**：[server/app/api/knowledge_runtime.py](../../server/app/api/knowledge_runtime.py)；[server/app/domain/knowledge_service.py](../../server/app/domain/knowledge_service.py)；[server/app/models/knowledge.py](../../server/app/models/knowledge.py)。

**测试位置**：[server/tests/test_app_lifespan.py](../../server/tests/test_app_lifespan.py)；[server/tests/test_knowledge_service.py](../../server/tests/test_knowledge_service.py)；[server/tests/test_ai_model_publication.py](../../server/tests/test_ai_model_publication.py)。

**用户文档**：[操作与失败处理](../user-guide/knowledge-system.md#kno)、[权限](../user-guide/roles-permissions.md)。

<a id="kno-004"></a>

## KNO-004 关键词、语义与混合检索

**目标与价值**：按业务问题定位可用文档片段，区分命中、覆盖不足与能力不可用。

**角色、前提与权限**：所有登录角色，包括VIEWER可发只读search POST；需要活动库及索引，语义/混合依赖可用EMBEDDING默认模型。

**操作、输入输出与状态**：输入查询、模式和分页；关键词BM25、语义有界精确余弦、混合RRF排序；返回片段、来源、分数及覆盖状态；打开原文证据。

**实现状态与限制**：已有实现；搜索范围是当前库；旧向量可标STALE，不伪装为当前可用。SQL向量存储不是独立向量数据库或无限规模服务；无全平台联邦全文搜索承诺。

**验证状态**：本轮关键词与证据流程通过；语义/混合本轮未执行外部模型验证。

**源码**：[web/src/views/knowledge/KnowledgeSearchPage.vue](../../web/src/views/knowledge/KnowledgeSearchPage.vue)；[server/app/api/v1/knowledge_retrieval.py](../../server/app/api/v1/knowledge_retrieval.py)；[server/app/domain/knowledge_retrieval.py](../../server/app/domain/knowledge_retrieval.py)；[server/app/domain/knowledge_ranking.py](../../server/app/domain/knowledge_ranking.py)。

**测试位置**：[server/tests/test_knowledge_retrieval.py](../../server/tests/test_knowledge_retrieval.py)；[server/tests/test_knowledge_ranking.py](../../server/tests/test_knowledge_ranking.py)；[e2e/knowledge-base.spec.ts](../../e2e/knowledge-base.spec.ts)。

**用户文档**：[操作与失败处理](../user-guide/knowledge-system.md#kno)、[权限](../user-guide/roles-permissions.md)。

<a id="kno-005"></a>

## KNO-005 基于引用的证据摘录问答

**目标与价值**：把已检索证据中的确切片段组织为可核对的回答，减少无来源陈述。

**角色、前提与权限**：所有登录用户可用answer只读POST；需要可用CHAT默认服务，以及所选检索模式需要的索引/模型。

**操作、输入输出与状态**：输入问题，先检索再让模型选择引用；仅接受命中片段的连续原文摘录；返回ANSWERED及引用或INSUFFICIENT_EVIDENCE，展示证据不足。

**实现状态与限制**：已有实现；不返回未经验证的自由生成正文，不是通用聊天/Agent。引用范围、长度和数量有校验；模型输出错误不等于没有知识。

**验证状态**：源码及测试位置已确认，本轮未调用真实模型，也未重跑模型夹具。

**源码**：[server/app/domain/knowledge_answering.py](../../server/app/domain/knowledge_answering.py)；[server/app/api/v1/knowledge_retrieval.py](../../server/app/api/v1/knowledge_retrieval.py)；[web/src/views/knowledge/KnowledgeSearchPage.vue](../../web/src/views/knowledge/KnowledgeSearchPage.vue)。

**测试位置**：[server/tests/test_knowledge_answering.py](../../server/tests/test_knowledge_answering.py)；[e2e/knowledge-ai.browser.ts](../../e2e/knowledge-ai.browser.ts)。

**用户文档**：[操作与失败处理](../user-guide/knowledge-system.md#kno)、[权限](../user-guide/roles-permissions.md)。

<a id="kno-006"></a>

## KNO-006 片段原文定位与人工图事实关联

**目标与价值**：让读者核对引用原文，并把补充知识连接到明确版本的已有图事实。

**角色、前提与权限**：登录用户读证据与原文；EDITOR/ADMIN关联；文档/库活动、片段非历史，图版本、实体和可选事实必须匹配。

**操作、输入输出与状态**：打开片段查看行号/段落或CSV记录、历史/归档标记；按文档修订人工关联graph_revision_id、entity_iri与可选fact_id；在图证据查看关联文档。

**实现状态与限制**：已有实现；不能创建或改变图事实，不是自动事实抽取或源库血缘。关联固定版本；每次图文证据查询最多50引用；未提供对应删除关联操作。

**验证状态**：本轮原文定位通过；人工关联所有组合本轮未重跑。

**源码**：[web/src/views/knowledge/components/EvidenceDrawer.vue](../../web/src/views/knowledge/components/EvidenceDrawer.vue)；[web/src/views/knowledge/components/GraphLinkForm.vue](../../web/src/views/knowledge/components/GraphLinkForm.vue)；[server/app/domain/knowledge_retrieval.py](../../server/app/domain/knowledge_retrieval.py)；[server/app/models/knowledge_links.py](../../server/app/models/knowledge_links.py)。

**测试位置**：[server/tests/test_knowledge_retrieval.py](../../server/tests/test_knowledge_retrieval.py)；[e2e/knowledge-ai.browser.ts](../../e2e/knowledge-ai.browser.ts)。

**用户文档**：[操作与失败处理](../user-guide/knowledge-system.md#kno)、[权限](../user-guide/roles-permissions.md)。

<a id="acc-001"></a>

## ACC-001 首个管理员、登录会话与可选注册

**目标与价值**：建立明确账号身份与可撤销会话，避免混淆默认账号与隔离预览。

**角色、前提与权限**：首个管理员在空账号库通过seed-admin初始化；公开注册默认关闭，开启后新用户为VIEWER。

**操作、输入输出与状态**：用户名或邮箱及口令登录，返回访问/刷新令牌；刷新轮转旧刷新令牌；登出撤销提交的会话令牌；/auth/config与/me供界面使用。失败限流按配置执行。

**实现状态与限制**：已有实现；无通用默认口令；seed-admin不重置已有账号。无SSO/MFA/组织租户。后端每次读取账号状态/角色，菜单不是权限边界。

**验证状态**：本轮临时空库初始化、重复初始化拒绝、登录与配置检查通过；全量会话攻击/限流组合未重跑。

**源码**：[scripts/seed_admin.py](../../scripts/seed_admin.py)；[server/app/api/v1/auth.py](../../server/app/api/v1/auth.py)；[server/app/domain/account_service.py](../../server/app/domain/account_service.py)；[server/app/models/account.py](../../server/app/models/account.py)；[web/src/stores/auth.ts](../../web/src/stores/auth.ts)；[web/src/views/auth](../../web/src/views/auth)。

**测试位置**：[server/tests/test_account.py](../../server/tests/test_account.py)；[e2e/account-admin-ui.spec.ts](../../e2e/account-admin-ui.spec.ts)；[server/tests/test_permissions_matrix.py](../../server/tests/test_permissions_matrix.py)。

**用户文档**：[操作与失败处理](../user-guide/knowledge-system.md#acc)、[权限](../user-guide/roles-permissions.md)。

<a id="acc-002"></a>

## ACC-002 个人资料与账号改密

**目标与价值**：维护自己的展示身份和口令，不越权更改角色。

**角色、前提与权限**：所有已登录角色；改密需要旧密码。

**操作、输入输出与状态**：编辑显示名与头像URL；提交旧/新密码；成功后保留当前访问令牌，撤销其他令牌（含刷新令牌），需要时重新登录。失败保留表单并记录账号审计。

**实现状态与限制**：已有实现；不提供个人自行改角色、用户名/邮箱全量编辑或组织权限设置；并非所有个人更新都有乐观修订。

**验证状态**：本轮浏览器资料与改密通过。

**源码**：[web/src/views/account](../../web/src/views/account)；[server/app/api/v1/accounts.py](../../server/app/api/v1/accounts.py)；[server/app/domain/account_service.py](../../server/app/domain/account_service.py)；[server/app/schemas/account.py](../../server/app/schemas/account.py)。

**测试位置**：[server/tests/test_account.py](../../server/tests/test_account.py)；[web/src/views/account/**tests**/c4-forms.test.mjs](../../web/src/views/account/__tests__/c4-forms.test.mjs)；[e2e/account-admin-ui.spec.ts](../../e2e/account-admin-ui.spec.ts)。

**用户文档**：[操作与失败处理](../user-guide/knowledge-system.md#acc)、[权限](../user-guide/roles-permissions.md)。

<a id="acc-003"></a>

## ACC-003 受控密码找回与一次性重置

**目标与价值**：在不公开口令的前提下恢复账号访问。

**角色、前提与权限**：通常由ADMIN为其他ACTIVE用户签发重置链接，经安全渠道转交；自己改密走账号安全。公开找回只在开发显式开关开启时可用。

**操作、输入输出与状态**：签发一次性token；用户提交新密码；使用后令牌失效并撤销旧会话。邮箱不存在与存在按找回契约处理，不谎称邮件已发送。

**实现状态与限制**：已有实现；没有邮件发送服务；默认忘记密码返回不可用。生产禁止暴露重置token；唯一管理员丢失访问且无其他管理员时没有产品内自助恢复路径，应走受控运维恢复。

**验证状态**：本轮浏览器管理员签发、重置及后续登录通过；实际邮件未实现。

**源码**：[server/app/api/v1/auth.py](../../server/app/api/v1/auth.py)；[server/app/api/v1/accounts.py](../../server/app/api/v1/accounts.py)；[server/app/domain/account_service.py](../../server/app/domain/account_service.py)；[web/src/views/auth/ForgotPasswordPage.vue](../../web/src/views/auth/ForgotPasswordPage.vue)；[web/src/views/auth/ResetPasswordPage.vue](../../web/src/views/auth/ResetPasswordPage.vue)。

**测试位置**：[server/tests/test_account.py](../../server/tests/test_account.py)；[e2e/account-admin-ui.spec.ts](../../e2e/account-admin-ui.spec.ts)。

**用户文档**：[操作与失败处理](../user-guide/knowledge-system.md#acc)、[权限](../user-guide/roles-permissions.md)。

<a id="sys-001"></a>

## SYS-001 管理员用户管理

**目标与价值**：发放账号并控制可用状态与全局职责。

**角色、前提与权限**：仅ADMIN访问；其他角色由前后端拒绝。

**操作、输入输出与状态**：按查询/角色/状态分页；创建用户、编辑角色/状态、签发他人重置链接。ACTIVE/DISABLED；禁用撤销会话。

**实现状态与限制**：已有实现；禁止自降级、自禁用和为自己签发重置；无用户删除端点、组织树、批量导入或自定义授权审批。不要把自保护解读为全部管理员并发管理已验收。

**验证状态**：本轮用户创建、角色状态及重置浏览器链通过；并发管理员组合未重跑。

**源码**：[web/src/views/system/users/UsersPage.vue](../../web/src/views/system/users/UsersPage.vue)；[server/app/api/v1/accounts.py](../../server/app/api/v1/accounts.py)；[server/app/domain/account_service.py](../../server/app/domain/account_service.py)。

**测试位置**：[server/tests/test_account.py](../../server/tests/test_account.py)；[e2e/account-admin-ui.spec.ts](../../e2e/account-admin-ui.spec.ts)。

**用户文档**：[操作与失败处理](../user-guide/knowledge-system.md#sys)、[权限](../user-guide/roles-permissions.md)。

<a id="sys-002"></a>

## SYS-002 固定角色及成员数查看

**目标与价值**：解释ADMIN/EDITOR/VIEWER职责，查看成员分布。

**角色、前提与权限**：仅ADMIN查看角色管理页。

**操作、输入输出与状态**：读取固定角色与人数；按本地语言显示说明。权限判断来自后端角色与操作规则，非用户自定义权限项。

**实现状态与限制**：已有实现；只有查看，无角色新建/删除/权限矩阵在线编辑；不是未完成的可编辑RBAC设计器。

**验证状态**：源码确认，M3角色页入口抽查通过；成员计数各组合未逐项实测。

**源码**：[web/src/views/system/roles/RolesPage.vue](../../web/src/views/system/roles/RolesPage.vue)；[server/app/api/v1/accounts.py](../../server/app/api/v1/accounts.py)；[server/app/api/v1/deps.py](../../server/app/api/v1/deps.py)；[server/app/models/enums.py](../../server/app/models/enums.py)。

**测试位置**：[server/tests/test_permissions_matrix.py](../../server/tests/test_permissions_matrix.py)；[server/tests/test_business_access.py](../../server/tests/test_business_access.py)；[e2e/m3-browser-flow.spec.ts](../../e2e/m3-browser-flow.spec.ts)。

**用户文档**：[操作与失败处理](../user-guide/knowledge-system.md#sys)、[权限](../user-guide/roles-permissions.md)。

<a id="sys-003"></a>

## SYS-003 AI服务配置与默认能力

**目标与价值**：为AI辅助和知识检索选择可控的协议兼容服务，集中管理凭据。

**角色、前提与权限**：仅ADMIN；准备OpenAI兼容base URL、模型名、版本、超时、密钥与CHAT/EMBEDDING能力。

**操作、输入输出与状态**：查询/筛选/新建/编辑/删除配置，启停，按能力显式选择默认；更新/删除/default需If-Match。密钥后端加密，输出仅has_key/掩码；默认禁用/删除会清空选择。

**实现状态与限制**：已有实现；保存和设默认不会测试远端。URL自动追加chat/completions或embeddings；换origin需替换或清空key；换向量模型版本后重处理，旧索引标过期。旧环境变量不能代替当前配置。

**验证状态**：源码与测试位置确认；本轮该页及真实模型均未浏览器验收。

**源码**：[web/src/views/system/ai-models/AiModelsPage.vue](../../web/src/views/system/ai-models/AiModelsPage.vue)；[server/app/api/v1/ai_model_configs.py](../../server/app/api/v1/ai_model_configs.py)；[server/app/domain/ai_model_service.py](../../server/app/domain/ai_model_service.py)；[server/app/core/ai_client.py](../../server/app/core/ai_client.py)；[server/app/models/ai_model.py](../../server/app/models/ai_model.py)。

**测试位置**：[server/tests/test_ai_model_configs.py](../../server/tests/test_ai_model_configs.py)；[server/tests/test_ai_model_runtime.py](../../server/tests/test_ai_model_runtime.py)；[server/tests/test_ai_model_publication.py](../../server/tests/test_ai_model_publication.py)。

**用户文档**：[操作与失败处理](../user-guide/knowledge-system.md#sys)、[权限](../user-guide/roles-permissions.md)。

<a id="sys-004"></a>

## SYS-004 账号审计与业务资产审计

**目标与价值**：按操作者、对象与结果定位账号和资产变化，支持问题调查。

**角色、前提与权限**：仅ADMIN读；系统自动写入约定事件，无前端任意编辑审计。

**操作、输入输出与状态**：在账号与业务资产视图中查询、过滤、分页；业务记录含动作、对象、前后版本、结果、错误码和correlation_id；账号记录含账户事件与来源。

**实现状态与限制**：已有实现；业务资产审计覆盖已登记的语义资产/映射/源/规则/图结果事件，不是所有读操作或知识文档/模型配置的统一审计。无审计认证、全量留存策略或不可篡改承诺。

**验证状态**：源码确认；M3审计页入口抽查通过；本轮未重跑所有事件留痕/筛选异常。

**源码**：[web/src/views/system/audit-logs](../../web/src/views/system/audit-logs)；[server/app/api/v1/asset_audit.py](../../server/app/api/v1/asset_audit.py)；[server/app/api/v1/asset_audit_context.py](../../server/app/api/v1/asset_audit_context.py)；[server/app/domain/asset_audit_service.py](../../server/app/domain/asset_audit_service.py)；[server/app/models/asset_audit.py](../../server/app/models/asset_audit.py)；[server/app/api/v1/accounts.py](../../server/app/api/v1/accounts.py)；[server/app/domain/account_service.py](../../server/app/domain/account_service.py)。

**测试位置**：[server/tests/test_asset_audit.py](../../server/tests/test_asset_audit.py)；[server/tests/test_account.py](../../server/tests/test_account.py)；[e2e/asset-audit.spec.ts](../../e2e/asset-audit.spec.ts)。

**用户文档**：[操作与失败处理](../user-guide/knowledge-system.md#sys)、[权限](../user-guide/roles-permissions.md)。
