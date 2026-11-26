# 数据接入、映射、运行与图谱功能台账

核验日期：2026-11-26；基于 `9222236` 及当前未提交工作区，非发布版本。

使用步骤见[数据到图谱指南](../user-guide/data-graph.md)，实测与限制见[核验记录](../maintenance/verification-2026-11-26.md)。以下每项同时记录实现、权限、状态和限制；未单独实测的组合不得用主链通过代替。

<a id="dat-001"></a>

## DAT-001 只读数据源配置与连接测试

**入口**：`/datasources`。

**用户目标与操作**：创建、查询、修改连接与测试状态；输入源类型及配置，输出脱敏连接信息与连接结果；删除前检查引用。

**角色与前置条件**：EDITOR/ADMIN维护，VIEWER可查看并调用不保存的连接测试；已保存连接测试会写状态，需写角色。后端可访问源库、凭据与平台元库分离。

**实现状态与限制**：已有实现；SQLite、PostgreSQL、MySQL连接器存在；PG源使用psycopg2、MySQL源使用pymysql，默认依赖未覆盖这两种源驱动；未实测外部库。凭据后端加密。

**验证状态**：源码已确认；测试文件存在。本轮M3浏览器主链通过，具体覆盖见核验记录。

**实现证据**：[web/src/views/data-integration/sources](../../web/src/views/data-integration/sources)；[server/app/api/v1/datasources.py](../../server/app/api/v1/datasources.py)；[server/app/domain/source_service.py](../../server/app/domain/source_service.py)；[server/app/connectors/sql.py](../../server/app/connectors/sql.py)。

**测试位置**：[server/tests/test_m2_datasource.py](../../server/tests/test_m2_datasource.py)；[server/tests/test_source_connector.py](../../server/tests/test_source_connector.py)。

**用户指南**：[操作与失败处理](../user-guide/data-graph.md#dat)。

<a id="dat-002"></a>

## DAT-002 元数据快照、差异与引用

**入口**：`/datasources/catalog`。

**用户目标与操作**：采集schema、表、字段、主外键形成版本快照；查看历史、最新结构、差异与表引用，辅助识别映射影响。

**角色与前置条件**：采集需EDITOR/ADMIN，读取需登录；连接成功且有读元数据权限。

**实现状态与限制**：已有实现；元数据快照不是数据快照；结构变更后需主动采集。表名反向引用查询的输入为table_name，需结合数据源/结构上下文核对；不能宣称自动跨系统血缘。

**验证状态**：源码已确认；测试文件存在。本轮M3浏览器主链通过，具体覆盖见核验记录。

**实现证据**：[web/src/views/data-integration/catalog](../../web/src/views/data-integration/catalog)；[server/app/api/v1/metadata.py](../../server/app/api/v1/metadata.py)；[server/app/domain/metadata_service.py](../../server/app/domain/metadata_service.py)。

**测试位置**：[server/tests/test_m2_metadata.py](../../server/tests/test_m2_metadata.py)。

**用户指南**：[操作与失败处理](../user-guide/data-graph.md#dat)。

<a id="dat-003"></a>

## DAT-003 实时样例预览

**入口**：`/datasources/preview`。

**用户目标与操作**：选择数据源与表，读取真实样例并显示返回条数、字段和截断提示；目录内嵌样例最多5行，独立预览可分页读取。

**角色与前置条件**：所有登录角色可调用只读预览POST；源连接与表有效。

**实现状态与限制**：已有实现；接口单次默认20行、最多100行，连接/查询有时限；样例不持久化，不是全量导出。页面只读不等于源数据已脱敏，当前没有逐字段访问控制。

**验证状态**：源码已确认；测试文件存在。本轮M3浏览器主链通过，具体覆盖见核验记录。

**实现证据**：[web/src/views/data-integration/catalog/preview](../../web/src/views/data-integration/catalog/preview)；[web/src/views/data-integration/catalog/components/CatalogSamples.vue](../../web/src/views/data-integration/catalog/components/CatalogSamples.vue)；[server/app/api/v1/preview.py](../../server/app/api/v1/preview.py)；[server/app/domain/preview_service.py](../../server/app/domain/preview_service.py)；[server/app/schemas/preview.py](../../server/app/schemas/preview.py)。

**测试位置**：[server/tests/test_m2_preview.py](../../server/tests/test_m2_preview.py)；[web/src/views/data-integration/catalog/**tests**/catalog-samples.test.mjs](../../web/src/views/data-integration/catalog/__tests__/catalog-samples.test.mjs)。

**用户指南**：[操作与失败处理](../user-guide/data-graph.md#dat)。

<a id="map-001"></a>

## MAP-001 映射草稿、字段与关系配置

**入口**：`/extraction`。

**用户目标与操作**：选择源与目标本体；维护实体字段映射、转换/空值策略、身份键、融合优先级，以及FK/JUNCTION/ASSOCIATIVE关系；保存草稿。

**角色与前置条件**：EDITOR/ADMIN；先准备源结构与目标本体。VIEWER可读。保存请求含发布if_match及可选if_edit_match，正式页面携带上下文令牌。

**实现状态与限制**：已有实现；一表多类型、一类型多表支持，但业务键融合要求显式策略；业务键不是任意数据去重。旧客户端省略可选编辑令牌时保护较弱；不宣称所有写接口统一If-Match。

**验证状态**：源码已确认；测试文件存在。本轮M3浏览器主链通过，具体覆盖见核验记录。

**实现证据**：[web/src/views/data-integration/mapping/MappingWorkbenchPage.vue](../../web/src/views/data-integration/mapping/MappingWorkbenchPage.vue)；[server/app/api/v1/mappings.py](../../server/app/api/v1/mappings.py)；[server/app/domain/mapping_service.py](../../server/app/domain/mapping_service.py)；[server/app/schemas/mapping.py](../../server/app/schemas/mapping.py)；[server/app/domain/fusion_policy.py](../../server/app/domain/fusion_policy.py)。

**测试位置**：[server/tests/test_m2_mapping.py](../../server/tests/test_m2_mapping.py)；[server/tests/test_edit_revision.py](../../server/tests/test_edit_revision.py)；[server/tests/test_m3_mapping_fusion.py](../../server/tests/test_m3_mapping_fusion.py)；[server/tests/test_fusion_attributes.py](../../server/tests/test_fusion_attributes.py)。

**用户指南**：[操作与失败处理](../user-guide/data-graph.md#map)。

<a id="map-002"></a>

## MAP-002 编译预览与发布冻结

**入口**：所属工作区内操作或后台/API能力，无独立路由。

**用户目标与操作**：编译草稿或发布版本获得实体/关系样例及摘要；发布生成不可变映射修订，固定目标本体与其资源版本，后续执行选择该修订。

**角色与前置条件**：EDITOR/ADMIN；目标本体已发布，映射通过目标、字段及端点检查。编译会持久化预览，不属于VIEWER只读POST例外。

**实现状态与限制**：已有实现；预览是有限样例，不保证全量执行成功。发布不自动升级已发布下游；删除会删除映射版本与预览，运行引用由外键约束阻断，不能保证所有引用冲突都有友好业务错误。未被运行引用的历史也可能随删除丢失，应先评估保留要求。

**验证状态**：源码已确认；测试文件存在。本轮M3浏览器主链通过，具体覆盖见核验记录。

**实现证据**：[server/app/domain/mapping_service.py](../../server/app/domain/mapping_service.py)；[server/app/domain/mapping_compiler.py](../../server/app/domain/mapping_compiler.py)；[server/app/api/v1/mapping_preview.py](../../server/app/api/v1/mapping_preview.py)；[web/src/views/data-integration/mapping/components/FrozenMapping.vue](../../web/src/views/data-integration/mapping/components/FrozenMapping.vue)。

**测试位置**：[server/tests/test_m2_compiler.py](../../server/tests/test_m2_compiler.py)；[server/tests/test_m2_mapping.py](../../server/tests/test_m2_mapping.py)；[e2e/audit-correction-flow.spec.ts](../../e2e/audit-correction-flow.spec.ts)。

**用户指南**：[操作与失败处理](../user-guide/data-graph.md#map)。

<a id="map-003"></a>

## MAP-003 AI映射建议与文本候选审阅

**入口**：`/extraction/ai-assist`。

**用户目标与操作**：基于结构和本体生成映射候选，逐条审阅、应用或丢弃；文本抽取候选事实仅用于审阅，不写入正式图事实。

**角色与前置条件**：EDITOR/ADMIN生成与应用；需可用CHAT默认模型、有效映射/本体上下文。已有建议读取遵循现有全局业务权限。

**实现状态与限制**：已有实现；模型输出是候选；应用到草稿后仍需人工核查、编译、发布与执行。文本候选不等于知识库文档索引或已入图的事实；真实外部模型效果未验证。

**验证状态**：源码已确认；存在本地模型协议测试，本轮未执行真实模型验证。

**实现证据**：[web/src/views/data-integration/mapping/ai-assist](../../web/src/views/data-integration/mapping/ai-assist)；[server/app/api/v1/ai.py](../../server/app/api/v1/ai.py)；[server/app/domain/ai_suggestion_service.py](../../server/app/domain/ai_suggestion_service.py)。

**测试位置**：[server/tests/test_m5_ai_suggestions.py](../../server/tests/test_m5_ai_suggestions.py)；[server/tests/test_ai_completion_safety.py](../../server/tests/test_ai_completion_safety.py)。

**用户指南**：[操作与失败处理](../user-guide/data-graph.md#map)。

<a id="run-001"></a>

## RUN-001 抽取运行、校验与结果保护

**入口**：`/extraction/runs`。

**用户目标与操作**：按发布映射修订、源和namespace运行四阶段抽取；查看SUCCESS/PARTIAL/FAILED、计数、隔离原因、历史记录及运行报告导出。

**角色与前置条件**：EDITOR/ADMIN发起；所有登录角色读取。映射已发布，冻结资源存在，源可达；运行报告携带冻结版本清单。

**实现状态与限制**：已有实现；零产出或严格失败策略不能发布当前结果；有隔离是否允许PARTIAL取决于执行策略。同步运行API与后台任务分别存在；报告导出为专门下载响应。

**验证状态**：源码已确认；测试文件存在。本轮M3浏览器主链通过，具体覆盖见核验记录。

**实现证据**：[web/src/views/data-integration/runs](../../web/src/views/data-integration/runs)；[server/app/api/v1/extraction.py](../../server/app/api/v1/extraction.py)；[server/app/domain/extraction_service.py](../../server/app/domain/extraction_service.py)；[server/app/domain/run_export_service.py](../../server/app/domain/run_export_service.py)。

**测试位置**：[server/tests/test_m3_extraction.py](../../server/tests/test_m3_extraction.py)；[server/tests/test_m3_pipeline.py](../../server/tests/test_m3_pipeline.py)；[server/tests/test_m3_instance_validation.py](../../server/tests/test_m3_instance_validation.py)；[server/tests/test_m4_run_export.py](../../server/tests/test_m4_run_export.py)。

**用户指南**：[操作与失败处理](../user-guide/data-graph.md#run)。

<a id="run-002"></a>

## RUN-002 异步任务、延后执行与协作取消

**入口**：`/extraction/tasks`。

**用户目标与操作**：提交立即或指定run_after的任务，查看PENDING→RUNNING→SUCCESS/PARTIAL/FAILED/CANCELLED、阶段进度与关联运行；待执行可取消，执行中在阶段边界协作取消。

**角色与前置条件**：EDITOR/ADMIN创建/取消，所有登录角色读；使用发布映射修订。

**实现状态与限制**：已有实现；为进程内2线程执行池与懒启动轮询，run_after是一次性时间不是cron。运行中进度/取消控制在进程内；重启后调度恢复、跨进程取消和多副本语义不能当作分布式队列保障。

**验证状态**：源码已确认；任务测试存在；本轮浏览器主链不代表跨进程/重启恢复通过。

**实现证据**：[web/src/views/data-integration/tasks](../../web/src/views/data-integration/tasks)；[server/app/domain/extraction_task_service.py](../../server/app/domain/extraction_task_service.py)；[server/app/models/extraction.py](../../server/app/models/extraction.py)。

**测试位置**：[server/tests/test_m5_extraction_tasks.py](../../server/tests/test_m5_extraction_tasks.py)；[web/src/views/data-integration/tasks/**tests**/extraction-tasks.test.mjs](../../web/src/views/data-integration/tasks/__tests__/extraction-tasks.test.mjs)。

**用户指南**：[操作与失败处理](../user-guide/data-graph.md#run)。

<a id="run-003"></a>

## RUN-003 受限追加增量与水位

**入口**：所属工作区内操作或后台/API能力，无独立路由。

**用户目标与操作**：以可信成功基线复制实体及来源证据，读取大于旧水位的新增行，形成新结果；失败不错误推进基线。

**角色与前置条件**：EDITOR/ADMIN创建增量任务；同发布映射、源、namespace与冻结配置；整数主键、整数递增水位、不可变追加数据。

**实现状态与限制**：已有实现；不支持任意updated_at时间戳、已有行更新/删除、业务键融合、via端点等组合；不满足条件明确拒绝，不静默全量回退。不是CDC或通用增量同步。

**验证状态**：源码限制已确认；定向测试存在，本轮未新增增量环境验收。

**实现证据**：[server/app/domain/extraction_incremental.py](../../server/app/domain/extraction_incremental.py)；[server/app/domain/extraction_task_service.py](../../server/app/domain/extraction_task_service.py)；[server/app/domain/extraction_service.py](../../server/app/domain/extraction_service.py)。

**测试位置**：[server/tests/test_m5_extraction_tasks.py](../../server/tests/test_m5_extraction_tasks.py)。

**用户指南**：[操作与失败处理](../user-guide/data-graph.md#run)。

<a id="grf-001"></a>

## GRF-001 图谱探索、布局、选择与路径

**入口**：`/graph`。

**用户目标与操作**：选择结果集、中心实体和邻域，过滤类型/派生边，搜索对象、切换布局、查看选中属性、路径与视图提示，使用焦点模式和显式缩放。

**角色与前置条件**：所有登录角色读取；需要成功结果集，视图依赖对象及关系语义。

**实现状态与限制**：已有实现；graph-view默认200节点/1000边，最大500/2000；邻域1或2度，截断视图不是全图。布局与路径服务有各自边界，不能把屏幕缺少节点解释为源库无数据。

**验证状态**：源码已确认；测试文件存在。本轮M3浏览器主链通过，具体覆盖见核验记录。

**实现证据**：[web/src/views/graph/browse](../../web/src/views/graph/browse)；[server/app/domain/graph_view_service.py](../../server/app/domain/graph_view_service.py)；[server/app/domain/graph_analysis_service.py](../../server/app/domain/graph_analysis_service.py)；[server/app/domain/graph_recommendation_service.py](../../server/app/domain/graph_recommendation_service.py)。

**测试位置**：[server/tests/test_m3_graph_view.py](../../server/tests/test_m3_graph_view.py)；[server/tests/test_m4_graph_analysis.py](../../server/tests/test_m4_graph_analysis.py)；[e2e/m3-browser-flow.spec.ts](../../e2e/m3-browser-flow.spec.ts)。

**用户指南**：[操作与失败处理](../user-guide/data-graph.md#grf)。

<a id="grf-002"></a>

## GRF-002 实体详情、来源证据与融合决策

**入口**：`/graph/entities`, `/graph/entities/:id`, `/graph/evidence`。

**用户目标与操作**：搜索实体并查看属性/事实，按事实或实体追溯来源连接、表、行键、字段、映射和运行；查看融合候选、冲突和采用值；按源行反向追溯。

**角色与前置条件**：所有登录角色读取；明确graph_revision_id/事实或实体IRI，依赖保留的冻结上下文与证据。

**实现状态与限制**：已有实现；人工文档关联不是抽取证据。历史证据需按其固定版本解释，不能拿当前资源详情替代。原始来源可能含敏感数据，当前不提供字段级权限。

**验证状态**：源码已确认；测试文件存在。本轮M3浏览器主链通过，具体覆盖见核验记录。

**实现证据**：[web/src/views/graph/entities](../../web/src/views/graph/entities)；[web/src/views/graph/evidence](../../web/src/views/graph/evidence)；[server/app/domain/evidence_service.py](../../server/app/domain/evidence_service.py)；[server/app/domain/fusion_service.py](../../server/app/domain/fusion_service.py)。

**测试位置**：[server/tests/test_m3_evidence.py](../../server/tests/test_m3_evidence.py)；[server/tests/test_fusion_attributes.py](../../server/tests/test_fusion_attributes.py)；[e2e/audit-correction-flow.spec.ts](../../e2e/audit-correction-flow.spec.ts)。

**用户指南**：[操作与失败处理](../user-guide/data-graph.md#grf)。

<a id="grf-003"></a>

## GRF-003 历史结果切换与差异

**入口**：所属工作区内操作或后台/API能力，无独立路由。

**用户目标与操作**：列出历史图谱修订，比较增删变化；将可发布历史结果设为当前，工作台、图谱与证据上下文随之切换。

**角色与前置条件**：所有登录角色读，EDITOR/ADMIN切换；目标必须满足发布/成功条件。

**实现状态与限制**：已有实现；当前结果集指针是全局的，非每用户独立工作分支；切换不重跑源库、不改写历史事实。差异不是任意版本自动合并。

**验证状态**：源码已确认；测试文件存在。本轮M3浏览器主链通过，具体覆盖见核验记录。

**实现证据**：[server/app/api/v1/extraction.py](../../server/app/api/v1/extraction.py)；[server/app/domain/graph_analysis_service.py](../../server/app/domain/graph_analysis_service.py)；[server/app/domain/extraction_service.py](../../server/app/domain/extraction_service.py)；[web/src/views/data-integration/runs/ExtractionRunsPage.vue](../../web/src/views/data-integration/runs/ExtractionRunsPage.vue)。

**测试位置**：[server/tests/test_m3_graph_revision.py](../../server/tests/test_m3_graph_revision.py)；[server/tests/test_m4_graph_analysis.py](../../server/tests/test_m4_graph_analysis.py)。

**用户指南**：[操作与失败处理](../user-guide/data-graph.md#grf)。

<a id="grf-004"></a>

## GRF-004 图谱视图模板与语义字段

**入口**：所属工作区内操作或后台/API能力，无独立路由。

**用户目标与操作**：保存图谱布局/语义字段配置，按本体与版本选择适用模板；识别失效模板并阻止错误应用，可删除模板。

**角色与前置条件**：读取需登录，保存/删除需EDITOR/ADMIN；有效本体发布版本和布局配置。

**实现状态与限制**：已有实现；绑定本体版本，不自动迁移到新版本；模板不等于图事实或语义资产装配模板。

**验证状态**：源码已确认；测试存在，本轮未独立验证每种模板和布局组合。

**实现证据**：[server/app/api/v1/graph_templates.py](../../server/app/api/v1/graph_templates.py)；[server/app/domain/graph_template_service.py](../../server/app/domain/graph_template_service.py)；[web/src/views/graph/browse/GraphBrowsePage.vue](../../web/src/views/graph/browse/GraphBrowsePage.vue)。

**测试位置**：[server/tests/test_graph_template_semantics.py](../../server/tests/test_graph_template_semantics.py)。

**用户指南**：[操作与失败处理](../user-guide/data-graph.md#grf)。
