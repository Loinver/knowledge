# 产品承诺、路由与功能闭环审计

日期：2026-11-06（Asia/Shanghai）

仓库：`/Users/linyer/Public/Private/knowledge`

基线：`3e729e4213db3cd61a2430aa49962f226e65f312`；开始与报告整理前 `git status --short` 均为空。

## 1. 结论与证据边界

核心资产、映射、抽取、图谱和账号均有实际 API、领域服务和持久化实现，不是只有页面骨架。但“业务人员不离开界面完成建模—规则—抽取—追溯—修正”的承诺仍存在确定断点：规则不能从界面挂入本体，已发布类型不能从界面进入下一次修订，历史结果集不能从界面设为当前；导入和核心模板核对只有后端能力。增量任务的界面缺少水位字段，三个聚合图形丢边，图谱差异漏掉属性和派生变化。

本报告覆盖全部 **37 个命名叶子页面**，另有 `/ontology` 重定向；管理员视角 **26 个侧栏目的地**（含工作台），3 个详情页、2 个账号菜单页、4 个认证页、2 个错误页。依据当前路由 `web/src/router/index.ts:39–216` 和导航 `web/src/layout/useNavigation.ts:45–145`，不沿用历史“19 路由、6 菜单”的计数。

证据分级：

- **已验证**：隔离纯函数/内存库探针复现下述 4 类缺陷（聚合布局涉及三个形态）；本次定向布局测试 23 项通过、后端筛选测试 5 项通过；只读 SQLite 表目录确认正式样例文件当前有 17 张业务表。
- **局部验证**：各模块逐层读取当前调用链与具体断言；这些静态证据可以证明入口缺失、数据丢弃和算法分支，不能替代完整浏览器验收。
- **未验证**：本代理没有运行 UI、全量 lint/test/E2E、真实 PostgreSQL/MySQL、LLM、生产环境；没有核验国标 PDF 原文或逐条迁移 demo 测试。主代理负责 UI 和工程结果。报告引用的未执行测试均标作“现有断言”，不冒称本次通过。

遵守根 `AGENTS.md`、`.agents/AGENTS.md` 及架构/API/测试/代码/i18n/安全许可约束，按 `code-review-safe-refactor` 只读取证。业务代码、真实数据和配置均未修改；仅写 `/private/tmp/knowledge-audit-20261106/` 的本报告及产品审计探针产物。没有提交、部署或外网数据操作。

优先级采用修复严重度：P1 阻断已承诺闭环或返回错误结果，P2 局部功能/可用性缺口。需求文档把若干图形列为“P0 形态”，这是**需求优先级**，不把所有图形欠缺自动升级为安全/数据完整性 P0。本代理不出具全局无 P0 结论；并发与后端安全由其他代理判断。

## 2. 可执行发现

### PC-01｜P1｜确定闭环断点：规则库无法通过界面接入本体和抽取

- **承诺**：核验清单 V-RU-02/03/05 与 12 步第 4 步（`docs/kg-platform-completeness-check-prompt.zh-CN.md:309–313,369`）。
- **证据**：`web/src/views/ontology/Ontologies.vue:317–324` 创建时固定 `rule_ids: []`；`:305–309` 编辑仅传标签/定义。检索整个 `web/src`（排除生成 schema）的 `rule_ids` 仅命中该空数组。`GovernanceRules.vue:249–298` 有保存、测试、删除，没有绑定本体。后端 `ontology_service.py:254–273` 能维护 `OntologyRuleRef`，`:385–409` 冻结规则引用，`extraction_rule_stage.py:99–126` 从引用载入规则。
- **触发/影响**：从干净系统只用 UI 新建校验和派生规则，再发布本体并抽取；新规则没有引用入口，不能参与该链路。已由 API 配好的规则不受“入口缺失”这一结论影响。
- **修复方向**：在本体草稿/设计器提供规则选择、已选规则及版本可见性，并通过现有更新契约保存；抽取后展示逐规则结果。
- **验收**：纯 UI 创建 DATA 与 DERIVATION 规则→挂入本体→发布→抽取→检查命中/派生计数与冻结规则版本；刷新后绑定仍在。补一条不能由 API seed 替代此步骤的 E2E。

### PC-02｜P1｜确定闭环断点：已发布实体/关系缺少“新修订”界面入口

- **证据**：`EntityDetail.vue:248–250,386–388,694–707` 只允许 DRAFT 编辑/发布；`RelationTypes.vue:172–185` 只提供草稿发布。`web/src/api/entity-types.ts:23–45`、`relations.ts:17–38` 均无 unpublish。全前端检索 `unpublish` 无业务调用。后端 `api/v1/types.py:183–191`、`relations.py:182–190` 已提供撤回；`resource_lifecycle.py:40–65` 保留历史并回 DRAFT；`status_service.py:59–70` 拒绝直接编辑 PUBLISHED。
- **触发/影响**：首次发布后修正属性、端点、基数；UI 无法进入下一版。关系列表仍显示编辑按钮，提交已发布对象会被后端拒绝。阻断 V-ET-06 与 V-TR-07。
- **修复方向**：接入既有生命周期动作，产品文案明确“编辑下一版、历史快照不变”；关联实体/子属性的联动是否足够由后端生命周期测试进一步验证，不仅增加按钮。
- **验收**：UI 发布 v1→进入修订→改属性/关系→发布 v2；旧本体/映射仍看到 v1。现有后端断言 `test_resource_lifecycle.py:93` 只覆盖服务链，不是 UI 证明。

### PC-03｜P1｜确定功能缺陷：增量开关无法配置水位，编辑还会丢失已有水位字段

- **证据**：`ExtractionTasks.vue:186–191,294–296` 只传 `incremental`；`MappingWizard.vue:485–516` 反序列化与 `:726–735` 序列化都没有 `incremental_field`。后端 `schemas/mapping.py:69`、`mapping_service.py:269–277` 支持该字段；`extraction_service.py:352–357,376–383` 只有字段和水位都存在才加过滤。
- **触发/影响**：UI 新配映射后勾增量，缺水位字段仍全量扫描；或打开 API 已配置的映射保存，字段被规范化过程丢弃。不能把复选框等同于 L-01 增量闭环。
- **修复方向**：映射逐实体表设置水位字段、校验类型/稳定性并无损读写；任务创建前展示实际增量范围，配置不完整时报明确错误。
- **验收**：API 预置字段→UI 保存仍保留；UI 从零配置→第二次只读取新增源行；失败不推进水位。`test_m5_extraction_tasks.py:122–183` 以测试代码配置字段，覆盖不到 UI 丢字段。

### PC-04｜P1｜探针复现：版本差异漏掉属性、边属性和派生边变更

- **证据**：`graph_analysis_service.py:28–60,152–166` 只对实体 IRI 集与直接事实 SPO 集做差；没有读取 attrs、props、DerivedEdge 或重复事实数量。UI `GraphBrowse.vue:778–797` 只显示这四种新增/删除计数。现有 `test_m4_graph_analysis.py:155–168` 只断言新增实体/边。
- **复现**：内存库创建两个版本，保持相同实体 IRI/SPO，仅改变实体属性、边属性并增加派生边；返回四种差异计数均为 0、所有列表为空。见 `product-diff-probe.log`。
- **影响**：第 12 步“修正规则/映射后对比”可能看不到实际修正；持股比例变化、派生规则变化尤其受影响。重复同 SPO 的关系数量变化也会被 set 折叠（静态证据，未单独运行该变体）。
- **修复方向/验收**：定义可稳定匹配的实体/事实身份，区分 added/removed/modified，直接/派生分开；覆盖 attrs-only、props-only、derived-only 和重复关系数量差异，保留截断总数。

### PC-05｜P1｜探针复现：本体模式图、桑基和弦图返回聚合节点，却未返回聚合边

- **证据**：`layouts/index.ts:443–482`、`:701–774` 将实例转为类型节点；计算过的类型边没有放入 `LayoutResult.edges`。`GraphCanvas.vue:29–31` 回退原始实例边；`graphLayout.ts:45–48` 因端点 IRI 不存在生成空路径。
- **触发/复现**：输入 a:Person→b:Company；schema/sankey/chord 均返回 Person/Company 节点、`edges_returned=null`，实际可绘制边数 **0/1**。见 `product-graph-probes.log`。现有布局测试 `graphLayout.test.mjs:157,254` 主要断言聚合节点，23 项全通过仍漏报。
- **影响**：G-16/G-18/G-19 关系消失，类型关系计数不可见。另 `GraphBrowse.vue:699` 将所有选择都交给实例 explore，类型节点下钻也需要区别处理。
- **修复方向/验收**：聚合布局返回与节点一致的边和计数；区分类型下钻与实例中心展开。三形态分别验证路径非空、端点存在、计数正确、类型点击得到该类型实例。

### PC-06｜P1｜探针复现：三节点及以上环路漏标中间节点

- **证据**：`layouts/index.ts:529–554` DFS 遇回边时只加入回边两端（`:543–545`），未加入栈路径。
- **复现**：a→b→c→a，a/c 进入内环，b 位于外部网格 `(1015,90)`；见图形探针日志。`graphLayout.test.mjs:204` 现有断言仅使用两节点环。
- **影响**：G-09 循环股权/循环交易漏标环成员。
- **修复方向/验收**：用路径回溯或强连通分量识别全部环成员；覆盖 3/4 节点环、尾链、不连通多环、自环，确认非环节点不误标。

### PC-07｜P1｜探针复现：供应链双重角色被错误放入供应方列

- **证据**：`layouts/index.ts:363–388` 声明双角色居中，却在 `:376` 先从 right 删除所有 left，`:377` 将“两边都不在”的孤立节点作为 middle。
- **复现**：supplier→self→buyer 得到 x=170/170/790；self 未居中。现有 `graphLayout.test.mjs:144` 只有单边两端场景。
- **影响**：G-17 核心“本企业—上游—下游”角色错误；双角色客商样例也不能按承诺显示。
- **修复方向/验收**：按用户中心/语义角色计算两侧与交集；双角色、孤立节点、双向交易都要验证，不依赖数组顺序。

### PC-08｜P1｜确定闭环断点：资产选择器只读首页，超过阈值无法完整装配

- **证据**：`Designer.vue:508–513` 按默认页拉取类型/关系/域和本体；`api/v1/types.py:88–112` 默认 50 且丢弃 `_total`。`MappingWizard.vue:573–579` 固定前 200 条类型/关系，`:603–608` 再用这些 brief 数组过滤本体引用；`web/src/api/mappings.ts:15–18` 固定 200；`datasources.ts:24–25` 不带页参数（默认 50）；任务页 `ExtractionTasks.vue:147–149` 使用这些列表。
- **触发/影响**：资产位于第 51/101/201 项之后，在设计器、映射或任务选择器里找不到；已绑定资源若不在截取窗口也可能无法被编辑器正确还原。
- **限定**：类型列表自身有后端 q 搜索，不能说“所有第 51 条资产永远找不到”；问题是未分页/无远程搜索的选择器和未加载的引用。装配模板资源接口的前端有分页读取，不归入这一问题。
- **修复方向/验收**：兼容现有数组契约，增加带总数分页与远程搜索，已选择 ID 单独补全；用 51/101/201/202 条边界数据验证可发现、可选、刷新保留。对应优化方案 `:73,90–97` 的明确承诺。

### PC-09｜P1（M4）｜确定闭环断点与范围不足：本体导入未接 UI，只能装配已存在资源

- **证据**：`api/v1/ontologies.py:235–254` 有 preview/apply；`web/src/api/ontology.ts:46–126` 无导入方法，全前端无导入调用。`ontology_import_service.py:141–145` 遇未知 IRI 要求 SKIP，`:156–163` 仅建立已有资源引用，不重建类型、关系、属性与约束。
- **触发/影响**：用户从 Turtle/JSON-LD 导入外部本体，没有 UI 入口；即使调 API，也不能在空库恢复新资源。当前能力应称“RDF 解析预览 + 既有资源装配”。
- **修复方向**：先明确支持的导入子集与冲突策略，补 UI 预览/逐项解决；如接受完整互操作承诺，再实现新增资源与依赖闭包恢复。
- **验收**：导出含属性、约束、关联实体的本体→独立空库从 UI 导入→重导出做语义等价比较。现有 `test_m4_import.py:98` 正是在验证未知资源需跳过；`test_m4_export.py:141,283` 的 RDF 回读不等于导入回库。

### PC-10｜P1（M4）｜确定闭环断点：核心模板核对只有后端入口

- **证据**：`api/v1/templates.py:155–166`、`core_check_service.py:15–105` 能按调用方 requirements/标准条款返回 PRESENT/MISSING/KIND_MISMATCH/ENTERPRISE_EXTENSION；`web/src/api/templates.ts:12–56` 与 `AssemblyTemplates.vue` 没有 core-check 调用或呈现。
- **触发/影响**：业务人员无法在界面逐项核对标准核心与企业扩展；V-ON-03/M-02 不闭环。
- **修复方向/验收**：接入核对结果与来源说明，明确核对基线从何而来；四种状态均在 UI 可见且可定位资源。`test_m4_templates.py:325` 有具体分类断言，但本轮没有执行它；国标内容正确性须另核原文。

### PC-11｜P1｜确定闭环断点：历史结果集可读取，无法从 UI 设为当前

- **证据**：后端 `api/v1/extraction.py:229–239` 提供 `/graph/{id}/switch`；`web/src/api/extraction.ts:9–36` 无该方法，全前端检索无调用。`ExtractionRuns.vue:29–51,96–103` 只下载运行报告；`GraphBrowse.vue:542–550` 数字输入选择历史 graph，仅改变阅读上下文。
- **触发/影响**：要恢复到上一成功结果集时需绕道 API；“看历史版本”不能替代 H-33/V-EX-04 的当前结果集切换。
- **修复方向/验收**：在成功运行/结果集详情增加设为当前动作、明确当前标识；UI 切换后工作台、默认图谱、默认实体列表同时指向历史版本；失败/不可发布版本不可切入。

### PC-12｜P2｜确定契约缺陷：版本差异抽屉再次打开会访问 undefined.length

- **证据**：`api/v1/extraction.py:219–226` 返回数组；`web/src/api/graph.ts:94–97` 手写成 `{items: ...}`；`GraphBrowse.vue:315–319` 首次打开把 `page.items`（undefined）赋给 revisions，第二次在 try 外求 `revisions.value.length`。
- **触发/影响**：版本请求成功后关闭并再次打开差异抽屉，watcher 报错。首次仍可手工填数字做 diff，不能夸大为整个 diff 从来无法使用。
- **修复方向/验收**：以生成契约统一列表形状，避免重复手写返回类型；用实际数组响应覆盖开/关/重开与空列表。本代理静态证明该分支，浏览器控制台由主代理复核。

### PC-13｜P1｜确定承诺缺口：追溯版本链只有编号，缺少冻结快照跳转和修正入口

- **证据**：`FactEvidence` 在 `models/extraction.py:176–179` 保存映射/本体/资源/规则版本；`evidence_service.py:158–174` 返回这些字段；`GraphEvidence.vue:133–169` 组装标签值，`:303–309` 以 span 展示，没有各层快照链接。`GraphReports.vue:157–158` 焦点 IRI 也是纯文本。
- **影响**：V-TR-03 的“任一层可点击且显示冻结快照”、V-KG-05 焦点定位和 V-TR-07 修正往返不能按承诺完成。源表/行键追溯和派生事实来源已有实现，不应整体判为“无证据链”。
- **修复方向/验收**：为冻结版本提供可读详情并从证据链定位，另提供明确的当前草稿修正入口；修改上游后历史证据跳转内容保持原样，焦点链接保留图谱版本。

### PC-14｜P1（平台承诺）｜确定覆盖缺口：审计只覆盖账号，不覆盖资产编辑/发布

- **证据**：`models/enums.py:79–90` 动作全是登录、密码、资料、角色/状态；全 `domain`/`api/v1` 检索 `AuditLog`/`record_audit` 仅账号链。写入 `account_service.py:189–208`，查询 `:764`；类型/本体/映射发布领域没有业务审计写入。
- **触发/影响**：修改/发布知识资产后，系统日志不能回答“谁在何时改/发布了什么”（V-PL-02，核验清单 `:353`）。已有账号日志和过滤并非占位。
- **修复方向/验收**：明确业务审计动作与对象/版本字段，事务内记录操作者和结果；由各角色执行修改/发布→管理员检索到对象及旧新版本，失败也按既定口径记录。M5 审计增强应与当前账号审计完成度分开。

### PC-15｜P2｜确定承诺缺口：视图模板仅保存布局/中心/深度/隐藏类型

- **证据**：`GraphBrowse.vue:180–216` 仅保存/应用 `center,depth,excluded_types,layout_id`；没有层级关系、度量、时间、地理属性选择器。`graph_template_service.py:75–80` 有本体版本 stale 标记，但不等于语义配置已接入。`layouts/index.ts:778–789` 地理布局按固定属性名称猜测。
- **影响**：V-KG-09/文档 `:231–233` 的“不改代码配置语义”没有完成；异名本体即使推荐相同，布局选取属性也未必相同。
- **修复方向/验收**：定义并消费按 IRI 指定的语义字段配置；改名本体使用同构字段映射得到同等结果；失效资源给可操作提示。已有 `test_m4_graph_analysis.py:372` 只验证持久化/stale，并未证明这些语义字段被布局消费。

### PC-16｜P2｜确定范围缺口：融合解释有来源行，缺少属性冲突值与决策过程

- **证据**：`extraction_service.py:501–515` 同 IRI 已存在时不再写 attrs；`:516–535` 为每个源行留 `_entity_attrs` 证据，但 object 是实体 IRI。`evidence_service.py:299–310` 返回此 IRI，并明确排除 `_entity_attrs` 的冲突比较。`test_m3_mapping_fusion.py:438–472` 断言来源表/行和贡献非空，没有断言不同源属性值。
- **触发/影响**：同业务键客商两个来源的名称等属性不一致，G-29 能解释“来自哪些行”，无法解释“各值是什么、为何保留此值”。不能用来源行数量证明字段融合决策完整。
- **修复方向/验收**：先定义首值/优先级/冲突隔离策略，再保存必要的属性级贡献与选值理由；两源同键不同名称应显示双方值、最终值、原因，重复抽取稳定。不得以真实原值全量日志替代受控证据模型。

## 3. 待专门确认的风险与增强，不计作已复现严重缺陷

| 编号/类型                       | 当前证据与边界                                                                                                                                                                          | 触发及影响                                                                       | 方向/验收                                                                                              |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| R-01 四态报告风险，移交后端代理 | `extraction_rule_stage.py:67–70` 跳过所有非 DATA；`:120–122` 本来为 SHACL/OWL 生成 NOT_RUN 原因；`test_m3_rule_derivation_stages.py:248–254,409–410` 用 MANUAL SHACL，未覆盖 AUTO SHACL | AUTO SHACL/OWL 被挂入本体时结果可能完全遗漏，无法辨别“未执行”；未声称其返回 PASS | 用 AUTO SHACL/OWL 隔离探针核验 report/counts，必要时保留逐规则 NOT_RUN；规则快照漂移问题交后端统一处理 |
| R-02 标准符合性边界             | `rdflib_backend.py:124–166` 真正执行 OWL 2 RL；`validation_service.py:321–365` 有范围信息；完整 DL 没有据此完成                                                                         | 将局部 RL PASS 宣传为完整国标/完整 OWL-DL 会超出证据                             | 明确 A08 的规则子集、状态和推理器能力；独立语义样例+标准原文验收。不能沿用旧文档声称 A08 永远 NOT_RUN  |
| R-03 增量/调度的产品边界        | 开关、一次性 run_after、后台任务已有；开发计划 `:369` 的稳定水位/重放去重/删除标记/失败重试四要素不是同义词                                                                             | 定时一次不能当周期调度；读取新行不能当含删除更新的增量快照                       | PC-03 先修配置；剩余增量/任务并发语义由后端代理与主代理验收，不在本报告用任务文件存在判全实现          |
| E-01 画布直接建模增强           | `Designer.vue:840` 新建类型已接入，关系要转关系库；现有拖拽装配/布局保存真实存在                                                                                                        | V-DS-03 连线建关系需跨页面，降低效率                                             | 保留现有跨页模式作为可用基线；若接收增强，再增加连线建关系及属性编辑，不声称设计器整体缺失             |
| E-02 AI/文档抽取范围            | `AiAssist.vue:74–80` DOCUMENT_FACTS 为 review-only；`ai_suggestion_service.py:356–376` 拒绝直接 apply；`test_m5_ai_suggestions.py:188–224` 断言此边界                                   | 文档事实建议不会直接形成知识图谱                                                 | 属 L-03/P2 规划；明确“建议审阅”文案，未来物化需校验、证据与发布流程；本次未接外部模型                  |
| R-04 领域双语真实性             | `Ontologies.vue:298` 英文为空时把中文写入 en-US；`GraphBrowse.vue:185` 模板两个语言存同名                                                                                               | 不再能区分缺译与真实英文，违反开发计划 `:413` 的缺译标识方向                     | 空缺语言保留空缺，通过显示层回退并标记；双语运行由主代理验证                                           |

## 4. 全部路由 → 页面 → API → domain → 数据 → tests

以下路径均相对本报告开头的仓库根。为避免每格重复长路径：页面列相对 `web/src/views/`；前端 API 相对 `web/src/api/`；后端 API 相对 `server/app/api/v1/`；服务相对 `server/app/domain/`；测试相对 `server/tests/`。API 地址通常带 `/api/v1` 前缀，统一响应客户端负责解包。

“基本链存在”表示读取了真实调用/持久化/断言，**不是本轮 UI 验收通过**。“承诺”是 M0–M4 主流程或 ADR 已采纳范围；“规划/增强”是 M5、核验清单新增范围，不因有路由就升级为完整承诺已兑现。

数据模型索引：`models/resource.py:30,49,92,123,138,164,208`（命名空间/资源/版本/继承/引用/属性）；`models/domain.py:28,55,72,95,121,146,162,176,200`（域/域版本/成员/本体/本体版本/资源引用/规则引用/布局/装配模板）；`models/data_access.py:29,49,66,89,113`（源/元数据/映射/映射版本/预览）；`models/extraction.py:30,55,85,103,126,148,182,221`（运行/图版本/实体/直接边/派生边/证据/任务/隔离）；`models/governance.py:23,61,87,111`（规则/视图模板/AI 建议/条款）；`models/validation.py:28,49`（报告/结果）；`models/account.py:28,61,85,104`（用户/令牌/恢复令牌/账号审计）。

| # / 路由（路由行号）                      | 入口与页面                                     | API → domain → 数据                                                                                                                        | 当前功能结论与承诺范围                                                                                                       | 现有具体测试覆盖 / 空缺                                                                                                     |
| ----------------------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| 01 `/`（48）                              | 侧栏工作台 → `Dashboard.vue`                   | `dashboard.ts`→`dashboard.py:19`→`dashboard_service.py:20–55`→全表聚合、当前图版本                                                         | H-60 承诺；真实总数与流程入口，非前端首页数组计数；全部问题直达的体验未实测                                                  | `test_dashboard.py:105` 全页总数/当前结果集，`:291,308` 失败不伪装空数据；未跑 UI                                           |
| 02 `/ontology/namespaces`（57）           | 实体类型组 → `ontology/Namespaces.vue`         | `namespaces.ts`→`namespaces.py:33–77`→`iri_service.py:35,157`→Namespace、ModelResource                                                     | H-03 承诺；登记、列表、删除保护有真实链；更名影响面 API 未接当前改名 UI                                                      | `test_m0_domain.py`、`test_iri.py`、`test_api_envelope.py` 的唯一性/保护断言；前端 `ontology/__tests__/namespaces.test.mjs` |
| 03 `/ontology/entity-types`（62）         | 实体类型组 → `ontology/EntityTypes.vue`        | `entity-types.ts:23–44`→`types.py:88`→`type_service.py:32,243,332`→资源/属性/统计                                                          | H-11 承诺；创建、搜索、统计、展示切换存在；选择/列表分页见 PC-08                                                             | `test_m1_entity_type.py:57,195,206`，`test_dashboard.py`；`EntityTypes.vue:257` 查询无页号                                  |
| 04 `/ontology/entity-types/:id`（67）     | 列表详情 → `ontology/EntityDetail.vue`         | get/update/rename/publish/usages→`type_service.py:224,381,479`、`iri_service.py:85`→资源/约束/继承/快照                                    | 六页签真实取数；来源条款/枚举版本可写；发布后演进断点 PC-02；继承 UI 仅直接 parent 名称链 `:659–661`，完整继承属性体验未证实 | `test_m1_entity_type.py:111,124,141,185,235`；`test_m4_prop_constraints.py:106,191,442,592`；并发另审                       |
| 05 `/ontology/relation-types`（72）       | 关系类型组 → `ontology/RelationTypes.vue`      | `relations.ts`→`relations.py`→`relation_service.py:49,82,178,240,366,570`→ObjectPropDetail、ASSOC、ResourceRef                             | H-12 承诺；端点、OWL、关联属性与发布真实写入；PC-02/08 阻断修订/完整选取                                                     | `test_m1_relation.py:105,139,177,211,262,314,395`；同实体对两条关联记录不是仅文件声明                                       |
| 06 `/ontology/relation-types/:id`（77）   | 关系详情 → `ontology/RelationDetail.vue`       | get/usages/publish→`relation_service.py:430,454` + usages→资源/域/本体/历史版本                                                            | 关系端点、约束、特征、引用/版本展示；无已发布修订入口                                                                        | `test_m1_relation.py:534,562` 使用与版本负载断言；未执行详情 UI                                                             |
| 07 `/ontology/domains`（82）              | 业务域组 → `ontology/Domains.vue`              | `domains.ts`→`domains.py`→`domain_service.py:21,56,85,119,293,354`→BusinessDomain、DomainMember、DomainRevision                            | H-10 承诺；域树/成员、唯一维护域、跨域引用、发布前检查；域成员与类型继承为不同模型                                           | `test_m1_domain.py:114,132,140,192,212,259`；全五域 UI 场景未跑                                                             |
| 08 `/ontology/ontologies`（52）           | 本体组 → `ontology/Ontologies.vue`             | `ontology.ts`→`ontologies.py`→`ontology_service.py:37,96,244,348,425`→OntologyRef/Revision；模板服务                                       | H-13/M-04 承诺；创建/元信息/装配引用/发布、另存模板存在；规则 PC-01，导入 PC-09，版本导航 PC-13                              | `test_m1_ontology.py:93,109,126,141`，`test_m4_templates.py:107`；不能以空本体创建证明完整装配                              |
| 09 `/ontology/designer`（87）             | 本体建模组 → `ontology/Designer.vue`           | ontology refs/layout/validate/publish→`ontology_service.py:323–348`→CanvasLayout 与语义资源分离                                            | H-13 承诺；资源池、拖入/布局/检查器/校验发布、创建类型存在；连线建关系需跳转（E-01），大库 PC-08，规则 PC-01                 | `test_m1_ontology.py:141` 布局不增语义版本；设计器全交互由主代理跑                                                          |
| 10 `/datasources`（94）                   | 抽取组 → `datasources/DataSources.vue`         | `datasources.ts`→`datasources.py:32–105`→`source_service.py:27,113,142,160` + connectors→Datasource                                        | H-20 承诺；新增/编辑/测试连接/删除使用真实服务；凭据、安全、远端连通性由专门代理核验                                         | `test_m2_datasource.py` 与 `test_source_connector.py` 连接/只读/凭据/删除保护断言；本次无真实远端                           |
| 11 `/datasources/catalog`（99）           | 抽取组 → `datasources/DataCatalog.vue`         | metadata API `:27–80`→`metadata_service.py:116,137,231,256`→MetadataSnapshot、MappingRevision                                              | H-21 承诺；采集真实表列外键、版本差异、映射反向引用；不是静态目录                                                            | `test_m2_metadata.py:76,99,126,151,231` 采集/差异/无凭据/引用；UI 四级下钻未实测                                            |
| 12 `/datasources/preview`（104）          | 抽取组 → `datasources/SamplePreview.vue`       | preview API→`preview_service.py:73` + readonly connector→源表受限读取                                                                      | H-22 承诺；受限样例数据；不能把 SQLite 测试等同远端数据库已验收                                                              | `test_m2_preview.py` 行数/字段/失败边界，`test_source_connector.py`；本次未新跑                                             |
| 13 `/extraction`（110）                   | 抽取组 → `extraction/MappingWizard.vue`        | `mappings.ts`→mappings/mapping_preview→`mapping_service.py:81,169,244,294`、mapping_compiler→MappingRevision/Preview                       | H-30/31 承诺；5 步、字段转换/空值、三类关系、预览与发布；PC-03/08；完整五场景 UI 未证实                                      | `test_m2_mapping.py`、`test_m2_compiler.py`、`test_m2_preview.py`；`test_m3_mapping_fusion.py:310,345,374` 融合/多态/边属性 |
| 14 `/extraction/runs`（115）              | 抽取组 → `extraction/ExtractionRuns.vue`       | `extraction.ts:10–22`→`extraction.py:96,169,186`→extraction_service/run_export_service→Run、GraphRevision、白名单报告                      | H-32/33、V-EX-08 承诺；运行列表/JSON 下载真实存在；无当前集切换 PC-11；详情反馈主要在向导/任务页                             | `test_m3_extraction.py`、`test_m3_pipeline.py`、`test_m3_graph_revision.py`、`test_m4_run_export.py`；UI 修正往返不覆盖     |
| 15 `/extraction/tasks`（120）             | 抽取组 → `extraction/ExtractionTasks.vue`      | `extraction.ts:23–35`→`extraction.py:116–160`→extraction_task_service→ExtractionTask、Run、水位                                            | M5 M-08/09、L-01/02 规划已有部分落地；状态/取消/一次性 run_after 存在，增量配置 PC-03；后台恢复/并发另审                     | `test_m5_extraction_tasks.py` 任务成功、取消、增量、失败水位；不能证明周期调度/完整四要素                                   |
| 16 `/extraction/ai-assist`（125）         | 抽取组 → `extraction/AiAssist.vue`             | `ai.ts`→`ai.py:29–99`→`ai_suggestion_service.py:103,173,282,356`→AiSuggestion、可应用草稿                                                  | L-03/04 规划增强；配置驱动的建议、应用/丢弃真实存在；文档事实仅审阅 E-02；没接外部模型本次不能验输出质量                     | `test_m5_ai_suggestions.py` stub LLM+校验+应用边界；不是在线模型验收                                                        |
| 17 `/graph`（131）                        | 图谱组 → `graph/GraphBrowse.vue`               | `graph.ts`→`extraction.py:68` + diff/path/recommendation + graph_templates→graph_view/analysis/recommendation/template→图版本/实体/边/配置 | H-40、M-10/13及 G 系列；全图/邻域/过滤/布局/导出/路径/矩阵/差异部分完成；PC-04～07/12/15 明确缺陷                            | `test_m3_graph_view.py`、`test_m4_graph_analysis.py:155,171,346,372`；本次23布局+5后端选择通过，另有反例                    |
| 18 `/graph/entities`（136）               | 图谱组 → `graph/GraphEntities.vue`             | graph API→`extraction.py:274`→extraction_service 查询→EntityIdentity                                                                       | H-41 承诺；实体服务端分页/搜索、图版本、详情入口存在；不属于 PC-08 的纯资产选择器                                            | `test_m3_extraction.py`、`test_m3_graph_view.py` 实体查询断言；UI未跑                                                       |
| 19 `/graph/entities/:id`（141）           | 实体详情 → `graph/GraphEntityDetail.vue`       | detail/evidence/fusion→`extraction.py:294,319` 等→extraction_service/evidence_service→属性、入/出边、派生、证据                            | H-41/G-30/G-29；五类基础页签+融合页；`:119–145` 可带版本/中心跳五种形态；不是业务分区完整360，PC-16                          | `test_m3_evidence.py`、`test_m3_mapping_fusion.py:438`；静态已核调用而非仅见文件                                            |
| 20 `/graph/evidence`（146）               | 追溯组/事实表 → `graph/GraphEvidence.vue`      | fact/entity/reverse trace→extraction API→`evidence_service.py:28,89,181`→FactEvidence/DerivedEdge/Quarantine                               | H-42 承诺；源行、转换、运行/版本号、隔离提示真实；快照导航与修正 PC-13                                                       | `test_m3_evidence.py`、`test_m4_graph_analysis.py:413` 源行反查；全链可点击未实现                                           |
| 21 `/graph/reports`（151）                | 图谱组 → `graph/GraphReports.vue`              | `validation.ts`→`validation.py:53,65,72`→instance_validation_service→ValidationReport/Result                                               | H-51 承诺；选择图版本、触发真实校验、四态统计/结果；焦点纯文本 PC-13；规则阶段结果与此报告完整汇总仍需后端核验               | `test_m3_instance_validation.py`、规则阶段测试；前端竞态另审                                                                |
| 22 `/governance/rules`（157）             | 规则组 → `governance/GovernanceRules.vue`      | `governance.ts`→`governance.py:29–97`→rule_service→Rule、版本/例子                                                                         | M-01 承诺；四种语言、来源/目标/严重程度/例子/测试真实保存；SHACL AUTO 例子用真实引擎；与本体断开 PC-01                       | `test_m4_rules.py`、`test_m1_rule_trace.py`、`test_m3_rule_derivation_stages.py`；规则语言不同不能统一要求“例子通过”        |
| 23 `/governance/clauses`（162）           | 规则组 → `governance/StandardClauses.vue`      | `clauses.ts`→`clauses.py:29–89`→clause_service→StandardClause                                                                              | M-03 承诺；标准编号/条款编号/自撰说明 CRUD；有存储不等于原文正确或所有解释差异齐备                                           | `test_m4_clauses.py` 元数据/引用断言；国标内容本轮未验                                                                      |
| 24 `/governance/enum-dictionaries`（167） | 实体类型组 → `governance/EnumDictionaries.vue` | enum-dictionaries API→`enum_dictionaries.py:35–117`→enum_dictionary_service→字典/不可变版本/引用                                           | M-05 承诺；字典显式版本引用、不可随上游静默更新、被使用信息；属性编辑已可选择                                                | `test_m4_enum_dictionaries.py`；`test_m4_prop_constraints.py:174` 显式字典版本、`test_m4_export.py:216` 冻结枚举导出        |
| 25 `/governance/templates`（173）         | 本体组 → `governance/AssemblyTemplates.vue`    | `templates.ts`→`templates.py:35–139`→template_service→AssemblyTemplate/资源版本                                                            | M-04 承诺；新建、内置只读/复制、资源 pin、实例化、另存模板；核心核对 PC-10                                                   | `test_m4_templates.py:107,153,198,316,325` 具体持久化/冲突/分类断言；后者无 UI                                              |
| 26 `/governance/export`（178）            | 本体组 → `governance/OntologyExport.vue`       | `ontology.ts` export→ontologies API→`ontology_export_service.py:40`+semantics→冻结本体/资源/枚举                                           | M-07 承诺；TTL/JSON-LD、include-shapes 导出真实；没有独立 SHACL-only 格式，但可包含 shapes；外部导入回库 PC-09               | `test_m4_export.py:141,283,309,438,503` 保留约束、冻结和头信息断言；未跑独立第三方工具                                      |
| 27 `/account/profile`（184）              | 头像菜单 → `account/Profile.vue`               | `auth.ts` profile→`accounts.py:40–57`→`account_service.py:619`→User+AuditLog                                                               | ADR0002 承诺；个人资料保存与当前用户刷新有真实调用；字段越权/竞态由安全/前端代理核验                                         | `test_account.py:469` 仅改已发送字段；`e2e/account-admin-ui.spec.ts:33` 存在UI步骤，本次未跑                                |
| 28 `/account/security`（189）             | 头像菜单 → `account/Security.vue`              | password→`accounts.py:59–79`→`account_service.py:639`→User/AuthToken/AuditLog                                                              | ADR 承诺；改密、当前会话/其他会话撤销有服务语义；设备会话列表不在ADR范围                                                     | `test_account.py:424` 改密保留当前并撤其他；UI生命周期测试未运行                                                            |
| 29 `/system/users`（195）                 | 管理员菜单 → `system/Users.vue`                | users/create/update/reset-link→`accounts.py:81–153`→`account_service.py:278,556,675,714`→User/ResetToken/AuditLog                          | ADR 承诺；分页筛选、新建、角色/禁用、管理员恢复链接真实；没有物理删除用户是当前生命周期选择                                  | `test_account.py:591,628,821,846,870,889`；UI admin lifecycle现有测试未运行                                                 |
| 30 `/system/roles`（201）                 | 管理员菜单 → `system/Roles.vue`                | roles→`accounts.py:155–164`→`account_service.py:757`→UserRole聚合                                                                          | ADR `:87–93` 固定 ADMIN/EDITOR/VIEWER 单角色与人数；无角色CRUD不是缺陷                                                       | `test_account.py:908` 人数与角色；资源/字段/租户权限属于另一期规划                                                          |
| 31 `/system/audit-logs`（207）            | 管理员菜单 → `system/AuditLogs.vue`            | audit→`accounts.py:167`→`account_service.py:764`→AuditLog                                                                                  | 账号审计承诺真实可筛选/分页；业务资产审计缺口 PC-14                                                                          | `test_account.py:924` 排序筛选；未覆盖业务资产写审计                                                                        |
| 32 `/login`（40）                         | 公开入口 → `auth/Login.vue`                    | `auth.ts`→`auth.py:60–106,148`→authenticate/issue/refresh/logout→User/AuthToken/AuditLog                                                   | ADR 承诺；用户名/邮箱、真实令牌/刷新/登出；安全性由专门审计，不以 UI 守卫当鉴权                                              | `test_account.py:198,231,253,282,327,351,666`；本次未跑登录UI                                                               |
| 33 `/register`（41）                      | 公开入口 → `auth/Register.vue`                 | config/register→`auth.py:37–58`→`account_service.py:253`→User/AuthToken                                                                    | 默认关闭公开注册；启用后注册 VIEWER。这是已采纳安全产品行为，不是“注册页不可用”缺陷                                          | `test_account.py:135,150,175` 默认/启用/管理员引导                                                                          |
| 34 `/forgot-password`（42）               | 登录页链接 → `auth/ForgotPassword.vue`         | config/forgot→`auth.py:108–132`→`account_service.py:536`→ResetToken（按配置）                                                              | 默认无邮件交付，界面按能力告知；生产用管理员恢复链接；不得把开发返回 token 当邮件已发送                                      | `test_account.py:500,556,591` 配置/不可用/管理员恢复                                                                        |
| 35 `/reset-password`（43）                | 恢复链接 → `auth/ResetPassword.vue`            | reset→`auth.py:135–145`→`account_service.py:583`→User/ResetToken/AuthToken                                                                 | ADR 承诺；一次性令牌、更新密码、撤销会话，页面真实调用                                                                       | `test_account.py:518,570` 消耗令牌/弱口令不提前消耗；邮箱在线投递未验且不在范围                                             |
| 36 `/forbidden`（213）                    | 路由守卫 → `Forbidden.vue`                     | 本地展示/导航；无领域写入                                                                                                                  | 账号导航基线，业务 API 权限另在后端                                                                                          | `test_permissions_matrix.py`、`test_business_access.py` 证明服务边界的断言；本次未遍历角色UI                                |
| 37 `/:pathMatch(.*)*`（216）              | 未知地址 → `NotFound.vue`                      | 本地404导航；无领域写入                                                                                                                    | 平台基线；不能以页面存在推断所有错误态/可访问性已验                                                                          | 由主代理路由冒烟；本代理未单独实测                                                                                          |

`/ontology`（router `:50`）只是重定向 `entity-types`，不另计业务功能。三个系统页面前端 `adminOnly`、菜单隐藏与后端权限是两层不同保证；安全代理负责后者的完整复核。

## 5. V-* 逐项功能完整性矩阵

本表采用“局部链存在 / 部分 / 断点 / 未验证”。严格清单的“✅ 已实现”要求浏览器操作、刷新持久和证据三者俱全，本代理未运行 UI，故不以静态审计给全项 ✅。

| 核验号  | 结论               | 当前证据和剩余验收                                                                                                                                                |
| ------- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| V-ET-01 | 部分               | 列表真实统计/搜索/域过滤 `EntityTypes.vue:257–276`，分页及大库选择 PC-08；卡片/图谱与状态筛选运行由主代理验                                                       |
| V-ET-02 | 局部链存在         | EntityDetail 六页签调用 get/usages；`type_service.py:381` 汇集规则/引用/版本；非静态占位，刷新UI未验                                                              |
| V-ET-03 | 局部链存在         | `EntityDetail.vue:355–382,560–562,1075–1077` 约束/来源条款读写；属性往返测试本次选择覆盖一项；所有数据类型组合未穷尽                                              |
| V-ET-04 | 部分               | 后端父类型/环路拒绝有测试；前端 `:659–661` 仅直接 parent 名称，不是递归祖先/继承属性完整证明；父选择及继承展示需补专项UI验收                                      |
| V-ET-05 | 部分               | 命名空间/草稿更名真实；`iri_service.py:85–154` 同步子属性/Rule.target_iri，id引用不需改；impact API `namespaces.py:76` 无UI预览；映射字符串与冻结安全由后端代理审 |
| V-ET-06 | 断点               | 后端修订锁/撤回/重发存在，前端新版本 PC-02；两标签页并发由前端代理核验                                                                                            |
| V-RT-01 | 局部链存在         | union/intersection、端点基数/方向、逆关系/OWL真实持久化，`relation_service.py:49,240,366`；测试 m1_relation/m4_prop_constraints                                   |
| V-RT-02 | 局部链存在         | ASSOC资源/端点/属性产生，`test_m1_relation.py:211,262` 与 `test_m3_mapping_fusion.py:374`；两条记录在UI图中可辨需运行验证                                         |
| V-RT-03 | 局部链存在         | 自引用与多类型端点模型、映射 discriminator 有实际代码与 `test_m3_mapping_fusion.py:345`；完整场景UI未跑                                                           |
| V-RT-04 | 部分               | 列表/详情/使用处/版本真实；发布后演进 PC-02、分页 PC-08                                                                                                           |
| V-RT-05 | 部分               | 推荐用端点/OWL/关联属性信号 `graph_recommendation_service.py:147–190`；缺显式语义配置 PC-15，不能把任何数字属性直接等同持股比                                     |
| V-BD-01 | 局部链存在         | 域树、唯一维护域、跨域引用为真实模型/断言（domain_service `:56,85,119`）                                                                                          |
| V-BD-02 | 局部链存在         | `domain_service.py:293–354` 发布检查/快照；不是仅按钮，整套复杂依赖未本次运行                                                                                     |
| V-BD-03 | 局部链存在         | DomainMember / ResourceParent / GraphTriple 三类表职责分离；全导出A02语义仍需独立检查                                                                             |
| V-BD-04 | 未验证全场景       | 源样例及脚本支撑五场景，但未从UI建立五域并核对共享同资源；不能拿seed代替                                                                                          |
| V-ON-01 | 部分               | 创建/元信息/模板实例化/另存模板有真调用；全版本列表与冻结详情导航 PC-13；来源字段需UI跑                                                                           |
| V-ON-02 | 局部链存在         | 按资源去重/pin/冲突检测，`ontology_service.py:96,348,425`，`test_m1_ontology.py:93,109`；冲突UI完整处理未证实                                                     |
| V-ON-03 | 断点               | PC-10 核心核对只在后端；标准核心清单准确性未核原文                                                                                                                |
| V-ON-04 | 断点/部分          | PC-09；导出保留属性/约束真实，独立解析回读与空库导入还原须区分                                                                                                    |
| V-ON-05 | 部分/语义边界      | A01–A08和四态领域实现；A08真跑RL，完整DL未实现（R-02）；不沿用旧“都未运行”结论                                                                                    |
| V-DS-01 | 局部链存在         | Designer资源池/布局、CanvasLayout独立持久化；大库截断 PC-08；拖拽、键盘、窄屏由主代理验                                                                           |
| V-DS-02 | 局部链存在         | 实体/关系检查器从资源详情和端点数据构建；全部字段/导航实测未做                                                                                                    |
| V-DS-03 | 部分/增强          | 画布创建类型已存在 `Designer.vue:840–879`；连线创建关系仍引导关系库，E-01                                                                                         |
| V-DS-04 | 部分               | 校验/发布存在；模板入口散在本体库/模板库；设计器面包屑与模板选择完整体验未运行                                                                                    |
| V-DS-05 | 部分/规划          | AI ontology completion有配置与建议应用，主要元信息/属性；不证明“自动补全全部关系”；E-02                                                                           |
| V-DS-06 | 断点/未验证        | 五场景资源能表达不等于设计器一次性做完；规则 PC-01、连线E-01、大库PC-08；全UI未验                                                                                 |
| V-RU-01 | 局部链存在         | GovernanceRules字段/来源/四种语言/例子实际保存；m4_rules覆盖；来源条款完整性未核原文                                                                              |
| V-RU-02 | 断点               | SHACL AUTO例子经真实引擎 `rule_service.py:137–158`；本体挂入UI缺失 PC-01                                                                                          |
| V-RU-03 | 部分/断点          | DATA算子命中/隔离服务存在；新UI规则不挂入；AUTO非DATA报告风险R-01；不能把基础I01–I06当全部场景规则                                                                |
| V-RU-04 | 未验证全场景       | 规则阶段有无环/合计/唯一键/必备端点/日期算子和测试；本轮未通过UI各录一条并抽取                                                                                    |
| V-RU-05 | 局部链存在但UI断点 | derivation_service支持 transitive/symmetric/co_occurrence/product_chain、DerivedEdge provenance；PC-01阻断新UI链                                                  |
| V-RU-06 | 部分               | 标准条款和source_reference持久化；四项解释差异和每次命中来源展示未完整验收                                                                                        |
| V-EX-01 | 局部链存在         | 源/元数据/预览真实实现；加密/只读/超时由安全代理直接核验；真实远端未验证                                                                                          |
| V-EX-02 | 部分               | 五步、双视图、转换/空值预览真实；大库PC-08、水位PC-03；全部未配置提示需UI                                                                                         |
| V-EX-03 | 局部链存在         | 三模式、自引用、多态、match_keys融合均非空壳；字段冲突解释PC-16；五场景全UI未验证                                                                                 |
| V-EX-04 | 部分/断点          | 幂等、失败保护、发布候选有现有断言；当前集恢复UI缺PC-11；本轮不重复全管线测试                                                                                     |
| V-EX-05 | 局部链存在         | Quarantine模型/字段/转换链、缺键/缺端点错误、默认值等有测试；规则焦点跳转PC-13                                                                                    |
| V-EX-06 | 部分               | 任务/取消/一次性调度/状态真实；增量UI PC-03；周期调度与完整L-01四要素未完成验收                                                                                   |
| V-EX-07 | 规划部分落地       | 文档事实建议/AI映射存在；文档不自动入图E-02；外部服务未验                                                                                                         |
| V-EX-08 | 局部链存在         | JSON导出真实、字段白名单test_m4_run_export；本轮未下载UI报告，安全另审                                                                                            |
| V-KG-01 | 部分               | 全图/1、2度/搜索/类型过滤/派生/平行边存在；关系类型、业务域过滤与更深UI未齐                                                                                       |
| V-KG-02 | 部分且有错误       | 五场景矩阵见第6节；PC-05/06/07直接反例                                                                                                                            |
| V-KG-03 | 部分               | 版本/导出/截断/部分键盘机制存在；任意边点击证据、关系/域过滤、完整图例未齐（第7节）                                                                               |
| V-KG-04 | 局部链存在         | 实体分页、详情属性/出入/派生/证据，`GraphEntityDetail.vue:105–185`；图版本带到中心展开                                                                            |
| V-KG-05 | 部分               | 四态统计/结果真实；焦点纯文本、严重程度/场景规则整合未证实，PC-13/R-01                                                                                            |
| V-KG-06 | 部分               | 组织树有位置算法；矩阵是类型计数，未有实例级矩阵或格子钻取                                                                                                        |
| V-KG-07 | 部分               | G01–G32全部逐项见第7节；不能按布局id个数宣称全完成                                                                                                                |
| V-KG-08 | 局部验证           | 本次执行 `test_layout_recommendation_is_rename_invariant` 通过；仅证明推荐服务指定结构案例，不证明所有图形/语义字段均改名不变                                     |
| V-KG-09 | 部分               | 模板CRUD/stale有实际模型；PC-15缺语义参数消费                                                                                                                     |
| V-KG-10 | 部分               | 路由query承载版本/中心/layout；360有五形态快捷按钮；全部筛选保持与业务分区联动未跑                                                                                |
| V-TR-01 | 局部链存在         | fact trace返回SPO、连接表行、字段、运行、类型；test_m3_evidence现有断言                                                                                           |
| V-TR-02 | 部分               | column_transforms记录源字段→目标/转换/参数（extraction_service `:528–535`）；多源值与选值解释不全PC-16                                                            |
| V-TR-03 | 断点               | 冻结版本号存在，任一层快照跳转缺失PC-13                                                                                                                           |
| V-TR-04 | 局部链存在         | DerivedEdge.rule_id/source_fact_ids（models `:126–145`）；具体推导规则与事实显示未全UI验                                                                          |
| V-TR-05 | 部分               | 源表某行reverse trace真实；图中的impact只是实例图反向树，不等同某映射/本体资源→运行→事实依赖分析                                                                  |
| V-TR-06 | 局部链存在         | evidence与详情quarantine提示；是否覆盖所有隔离组合未跑                                                                                                            |
| V-TR-07 | 断点               | PC-01/02/04/11/13共同阻断修正、重发、重跑、完整对比                                                                                                               |
| V-PL-01 | 局部链存在         | Dashboard真实库级聚合，现有全页/失败断言；全部问题直达UI未跑                                                                                                      |
| V-PL-02 | 部分               | 权限后端专门审计；账号日志真实，业务资产审计PC-14                                                                                                                 |
| V-PL-03 | 未验证全量         | 本轮未跑i18n gate/双语路径；R-04明确发现伪英文存储；交主代理                                                                                                      |
| V-PL-04 | 局部验证           | 本轮23前端+5后端定向结果；无全套、无demo逐断言映射。历史测试数不继承                                                                                              |
| V-PL-05 | 未验证             | 许可审计/例外由主代理工程审计；不以ADR里的许可表直接背书实际依赖                                                                                                  |

## 6. 五场景 × 六环节矩阵

当前 `samples/seed.sql` 与只读打开的 `samples/enterprise_demo.sqlite` 有 17 张业务表。`samples/README.md:18–22` 列出所需五场景结构；`:35–36` 仍称 SQLite 为旧六表快照，已与当前表目录不符。这里只查询 sqlite_master，未重建或修改该文件。`scripts/seed_five_scenarios.py` 是 API 灌入工具，不能证明从 UI 完成建模。

| 场景      | 本体表达                                                      | 源数据                                                             | 映射                                                  | 抽取                                                        | 图谱形态                                                                                               | 追溯                                                                      |
| --------- | ------------------------------------------------------------- | ------------------------------------------------------------------ | ----------------------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------- |
| 部门/组织 | 自引用/传递/逆关系、ASSOC任职可表达；域与继承分离；完整UI未验 | org_department/position/employment存在；seed包含四层/多树/孤儿情形 | FK、自引用、带属性任职均有实现；纯UI五场景配置未验    | DATA无环等算子与基础实例校验存在，规则UI挂入PC-01阻断新建链 | org_tree/indent_tree有分层；缺折叠与完整业务层级聚合；三节点cycle漏标PC-06；时间形态见G22/23           | 直接边源行/任职属性转换可返回；版本钻取PC-13；任一边画布直达缺失          |
| 股权      | 多态PERSON/ENTERPRISE股东、带比例关系/派生链可表达            | eq_shareholder/eq_equity_holding存在；合计异常数据在seed           | discriminator多态端点、关联属性转换有真实代码和测试   | product_chain派生/比例合计DATA算子存在；规则UI断点          | equity_tree分层、control_chain优先派生；缺阈值/穿透控制；cycle错误，sankey丢边；属性变更diff漏报PC-04  | DerivedEdge保留rule/source_fact_ids；历史规则快照可点击与完整比例解释未验 |
| 人物关系  | 对称关系、高管任职、关联日期可表达                            | person_relation/org_executive_role及hr_employee存在                | 三关系模式、任职关联表可配置；全UI未验                | 同事co_occurrence/对称派生存在；规则挂入断点                | force/ring/最短路径真实；community只是连通分量，非稠密社区；甘特按类型分lane，不能直接证明同人重叠检测 | 实体来源/出入边/派生证据存在；任意图边点击证据缺失                        |
| 客商      | 同一实体类型+业务键跨表复用，双角色可表达                     | crm_customer/supplier/trade_transaction；同信用代码双角色数据      | match_keys跨表融合有定向测试（m3_mapping_fusion:310） | IRI合并可产出；冲突选值/贡献不完整PC-16                     | supply_chain双角色摆错PC-07；sankey/chord聚合边丢失PC-05；geo仅分块无地图                              | 融合来源行真实，但属性冲突值/最终选值理由不完整；反向源行可查             |
| 合同      | 合同/项目/主体，多方角色和补充协议自引用可表达                | ct_contract/party/project及经办人、父合同字段在seed                | FK/中间表/带属性关系可表达；三方及同对多记录全UI未验  | 关联属性/必备端点/日期规则代码存在；规则UI挂入断点          | timeline基于首日期；gantt用所有ISO日期最小/最大；nary按度数排布，未绑定多方角色语义                    | 来源表行/转换可查；源→修正→差异链仍受PC-02/04/13影响                      |

上述“可表达/代码存在”不是五场景验收成功。主代理应至少每场景用一个真实产物完成 UI 建模、抽取、主形态、事实证据验证，再决定是否提升为已实现。

## 7. G-01～G-32 全形态矩阵

布局代码简称 `L` = `web/src/views/graph/components/layouts/index.ts`；`GB` = `web/src/views/graph/GraphBrowse.vue`；`GC` = `.../components/GraphCanvas.vue`。当前注册表 `L:1327–1354` 有 24 个布局 ID；其余功能有的以抽屉/详情提供。**ID、按钮、测试名称不等于该形态的产品语义完整。**

| 编号/形态       | 当前真实能力与位置                                              | 相对承诺的结论/缺口                                        | 关键补验                                      |
| --------------- | --------------------------------------------------------------- | ---------------------------------------------------------- | --------------------------------------------- |
| G-01 组织树     | `L:210–255` DAG层级、折线边，环图有降级                         | 部分；缺折叠、分支统计和用户选择层级关系                   | 四层、多根、孤儿、折叠后计数与证据            |
| G-02 缩进树     | `L:258` 横向树布局                                              | 部分；不是可展开/收起的目录树                              | 展开收起、键盘树语义、节点数量                |
| G-03 旭日图     | `L:993` 类型/实例环形分区、marks                                | 部分；组织/业务域层级未作为层级源；缺真正聚焦缩放/返回层级 | 同本体多层关系聚合与钻取，质量叠加            |
| G-04 矩形树图   | `L:1041` 类型/实例面积分区                                      | 部分；未配置业务度量/域层级，缺多级钻取                    | 金额/数量不同度量面积编码和图例               |
| G-05 圆形打包   | `L:1087` 类型内实例圆                                           | 部分；按类型聚合而非任意业务树，缺层级聚焦                 | 父子归属/多根/回退及实例追溯                  |
| G-06 股权穿透   | `L:345` 通用分层，GC边属性标签                                  | 部分；未见持股比例阈值、逐层穿透控制                       | 多态股东、不同持股比、平行持股/环路           |
| G-07 实控人链   | `L:354–359` 有带props派生边则用其定层                           | 部分；不是完整控制权判定、阈值计算UI                       | 直接/间接比例、路径乘积与规则证据             |
| G-08 集团族谱   | `L:514` 通用分层组合                                            | 部分；尚未绑定指定族谱关系或折叠语义                       | 多父/共享子公司与业务层级选择                 |
| G-09 环路检测   | `L:529–576` DFS+内外圈                                          | **确定错误 PC-06**：三环漏中间点                           | 三/四节点、尾链、多个环/自环                  |
| G-10 力导向     | `L:132` d3力计算后输出坐标                                      | 部分；不是持续可拖节点力模拟；语义过滤/画布边详情不足      | 多重边、方向/对称、拖动/定位、证据            |
| G-11 自我中心   | `L:104` distance0/1/2分圈，GB `:530–535` 深度1/2                | 基础能力存在但部分；更深扩展/逐点展开的完整需求未满足      | 上下文保持、重边、不存在中心/截断             |
| G-12 路径查询   | `graph_analysis_service.py:63` 最短路径；GB `:288–297`，UI max6 | 局部验证；有向最短路径，未见全路径/按关系过滤              | 无路径、派生可选、关系过滤、证据链            |
| G-13 二部图     | `L:523` 横向层级排布                                            | 部分；不能据此证明任意用户选择两类型与多对多编码           | 两类型/中间实体/多重关系，角色选择            |
| G-14 社区聚类   | `L:613` 按连通分量分块                                          | 部分；连通分量≠稠密社区算法，缺社区超节点折叠              | 一个连通网络含两个密集团体的反例              |
| G-15 多方关系   | `L:653` 根据节点度数把枢纽置内圈                                | 部分；没有按语义端点角色≥3明确绘制多方关联                 | 合同三签约方、角色及同对多记录                |
| G-16 本体模式   | `L:443–482` 类型聚合                                            | **确定错误 PC-05**；聚合边未交渲染；下钻把类型IRI当实例    | 每种类型关系真实路径/计数与类型钻取           |
| G-17 客商供应链 | `L:364–389` 两列+middle                                         | **确定错误 PC-07**；双角色留左，孤立节点进中间             | 企业中心、双角色、交易金额/方向               |
| G-18 桑基       | `L:746–751` 类型聚合分层                                        | **确定错误 PC-05**；且普通边不是按金额带宽的完整桑基       | 可见聚合边后再验量宽、守恒/图例               |
| G-19 弦图       | `L:756–774` 类型节点圆周排布                                    | **确定错误 PC-05**；未见弦带/权重面积实现                  | 聚合计数/带宽/选择到实例证据                  |
| G-20 邻接矩阵   | `GB:384–415` 类型对计数表                                       | 部分；不是实例级矩阵，格子无钻取                           | 类型/实例切换、点击单元格到对应事实           |
| G-21 时间轴     | `L:403–411` 取首个可识别日期，按类型排lane                      | 部分；不能不配置就保证选到签订日/任职日                    | 多个日期属性、缺失/非法日期、指定时间属性     |
| G-22 任职甘特   | `L:1126–1194` 所有ISO日期min/max，lane按类型，重叠比较同类型    | 部分；不能据此认定“同人任职冲突”，不同人的记录也在同类比较 | person维度分组、明确start/end、开放区间       |
| G-23 时间回放   | `GB:448–496` 日期滑块过滤首日期与边端点                         | 部分；非有效期图谱重建，也无完整自动播放/时点对比          | 已结束任职/合同到期、同一时点有效边集合       |
| G-24 版本差异   | backend diff + GB抽屉                                           | **确定错误 PC-04**；PC-12响应形状；仅增删集不足            | 属性/派生/多重事实修改、抽屉重开              |
| G-25 地理分布   | `L:778–789` 固定区域属性名称→网格分块                           | 部分；无真实底图/经纬度，改名不变性不足                    | 配置区域属性、未知区域、地理坐标/图例         |
| G-26 证据链     | GraphEvidence版本/来源信息、事实表链接                          | 部分；PC-13冻结快照只显示编号；任意画布边不可点证据        | 任意层冻结快照、当前修正入口                  |
| G-27 影响面     | `L:876` 实例边反向树                                            | 部分；不是本体资源→映射→运行→事实的依赖影响图              | 修改一个资源显示真实受影响映射/运行及版本     |
| G-28 质量叠加   | `GB:244` 隔离IRI集，`GC:331`普通节点标记                        | 部分；`GC:209–273` marks分支没消费flagged，分区图缺质量层  | 在旭日/矩形树/打包等同一违规节点都可见/可定位 |
| G-29 融合解释   | `evidence_service.py:235–352` +实体详情fusion                   | 部分；源行真实，PC-16字段冲突与选择理由缺失                | 同键多源不同值、最后选值/来源和规则           |
| G-30 实体360    | `GraphEntityDetail.vue:119–185` 基本页签+五形态快捷按钮         | 部分；不是股东/投资/客商/合同/人员/风险各业务分区          | 分区完整性、对应形态、保留版本/选中实体       |
| G-31 小多图     | `L:1234` 选最多实例类型、按度前6、一实体仅放一次                | 部分；不是用户选多个中心，无法完整比较共享邻居             | 选定两中心共享邻居应在两图出现、同比例尺      |
| G-32 中心性排行 | `GB:423–445` 入度/出度/总度top30，点击explore                   | 部分；未见中介中心性与节点大小编码                         | 度/中介指标区分、过滤集合口径、节点定位       |

共性标准复核（核验文档 `:238–247`）：

- 版本通过 query 和数字输入可读；历史设为当前另缺 PC-11。所有形态数据来自当前请求结果，但聚合形态边错误不能视为数据正确。
- 图例有类型色和部分边属性，完整关系/直接派生/度量编码图例需 UI 核验；不要用一种颜色图例代表所有业务语义。
- `GB:687` 有截断提示、`:691` 有空态；日期不足/缺语义时能否说明补充路径并未全验。
- `GC:276–305` 边 path 没有 click/键盘入口；节点可选并不满足“任意节点或边能开详情证据”。下方 GraphFactTable 有事实证据链接，但它是绕路。
- marks分支的质量层见 G-28；PNG/SVG函数存在，CSV `GB:349–354` 仅导出节点 iri/type_iri/row_key，不含关系、属性和证据，不能据此宣称全量图数据导出。
- 明暗、双语、窄屏、焦点与全部形态键盘验收由主代理承担。本代理不引用历史截图作当前结果。
- 历史规模测试耗时不可继承为当前性能承诺；本次未压测。所有 G 项按严格通用标准最多“部分/局部验证”。

## 8. 12 步主流程的当前证据链

| 步骤                   | 静态/现有测试证据                                                                                     | 本轮判定                                                            |
| ---------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| 1 类型及属性           | `e2e/m3-ui-modeling-flow.spec.ts:221` 从命名空间到类型；后端属性测试                                  | 基础UI测试脚本存在；本轮没跑，五场景全部属性未证实                  |
| 2 关系                 | 同UI脚本有关系创建/发布；m1_relation和多态测试                                                        | 基础链存在；所有自引用/多态/对称/传递组合UI未验                     |
| 3 五域+本体            | UI脚本走业务域，到`:310`附近为删除域与空本体增删；`m3-browser-flow.spec.ts:67,430` 用seedOntology API | **不能证明全程UI装配完整本体**                                      |
| 4 校验/派生规则挂入    | 规则页真实CRUD；本体创建固定rule_ids空                                                                | **PC-01断点**；DATA/DERIVATION规则测试与SHACL例子应分别定义通过条件 |
| 5 数据源/元数据        | 后端m2测试，主流程脚本含界面接入                                                                      | 局部链存在；本轮未跑UI/真实远端                                     |
| 6 所有模式映射         | m2 compiler/preview与m3融合测试；向导真实请求                                                         | 部分；大库/水位问题；五场景全UI未验                                 |
| 7 抽取及规则结果       | extraction + DATA/DERIVATION实际服务与现有测试                                                        | 局部链存在；UI规则无法新挂入，AUTO SHACL报告R-01待核                |
| 8 幂等重跑             | 主流程脚本含API操作与后端断言，非全程UI                                                               | 有后端证明材料；本轮未重新跑完整管线                                |
| 9 失败保护/恢复        | 后端graph_revision/pipeline断言；UI无switch_current                                                   | 保护需合并后端报告；**恢复UI PC-11断点**                            |
| 10 五场景主/辅形态     | 24布局ID+抽屉/详情；本轮23布局测试通过但另有反例                                                      | **PC-05/06/07确定错误**；其余按第7节部分                            |
| 11 每种视图追溯        | 事实表/实体详情/追溯页有真实链                                                                        | 部分；任意画布边点击和冻结快照跳转不足                              |
| 12 隔离→修正→重跑→差异 | 映射可保存新草稿；资源修订UI缺；diff只看增删                                                          | **PC-02/04/13断点**，不满足完整修正闭环                             |

`e2e/m3-ui-modeling-flow.spec.ts:6–17` 自身注明只负责上半段建模，既有主流程前置为 API；不能把两个脚本合起来就称“全 12 步纯 UI”。`e2e/account-admin-ui.spec.ts:33` 则有独立账号生命周期测试，应单独运行、单独计覆盖。

## 9. 产品承诺与文档冲突

| 来源                                                                   | 当前有效需求/决策                                         | 冲突或过期声明                                                                                                                         | 建议校准                                                                                               |
| ---------------------------------------------------------------------- | --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `development-plan.zh-CN.md:14,323–365,369`                             | M0–M3资产/接入/抽取主链；M4规则/模板/导入导出；M5运营增强 | `:14`称全部47项到v1，`:365`把v1设M4但`:369`仍留大量M5；`:317`残留Element Plus、`:319`DCO、测试表Vitest与当前NaiveUI/Node测试规范不一致 | 将“首发承诺、已落地增强、后续规划”拆开；以当前AGENTS及实现作为工程规范；不要按旧里程碑数字给每项打完成 |
| `kg-platform-completeness-check-prompt.zh-CN.md:13,41,238–247,362–377` | 纯UI闭环、五场景、32形态的严格验收标准                    | 历史基线`:385–389`仍有两布局/无边属性/六表等旧描述；要求每种形态通用证据，历史报告却常按布局存在计实现                                 | 这些条目是要验证的承诺而非当前事实；仍要求本次UI/语义/数据证据                                         |
| `kg-platform-acceptance-2026.zh-CN.md:11,112`                          | 历史验收记录                                              | 称12步界面/主链打通；当前PC-01/02/11和现有E2E范围不支持该全称结论                                                                      | 保留历史记录日期，追加当前版本差异；声明API预置部分和未覆盖步骤                                        |
| `kg-platform-remaining-tasks.zh-CN.md:66–72,150–160,209–213`           | 历史待办用于提示检查                                      | B10段落既称完成又称停滞；旧表某些B项缺失但后文又记录落地；静态看到任务文件就称增量/调度闭环；旧dirty/lint结论不适用于干净当前HEAD      | 把旧清单当线索。本次已重新确认来源条款、草稿改名、画布新建类型、融合来源页等已存在，不重复报“完全缺失” |
| `optimization-execution-plan.zh-CN.md:11–21,65–76,90–107`              | 分页、权限、凭据、抽取规模、任务反馈具体目标              | 顶部说账号安全已落地，表格仍有待实施；“201条可选”当前仍有反例PC-08；历史测试数/压测值不代表本轮                                        | 用本轮代码/测试刷新单一状态表；把真实PG/MySQL/规模/SLA等未给定输入继续标未验证                         |
| `adr/0001-backend-stack.md:20–21,31–33`                                | RDF/SHACL真实执行、RL最小推理、完整符合性前需真实语义能力 | A08旧策略要求未执行，但当前RL真实跑且有scope；可选DL方案和许可不能仅凭ADR一行当事实                                                    | 明确“RL子集已执行/完整DL未实现”，统一API四态与产品文案；许可由工程审计按实际组件确认                   |
| `adr/0002-account-auth.md:87–106`                                      | 三档单角色、后端权限、默认关闭公注、管理员恢复、账号审计  | 与通用“系统管理”想象中的动态角色/权限点/邮件/设备列表不同                                                                              | 以ADR明确范围为账号验收标准；动态角色、多角色、邮件、验证码、设备列表是后续增强，不列当前缺陷          |

未出具标准符合性结论：本报告没有核验 `demo/GBT+48000.3-2026本体建模标准.pdf` 原文；核心核对服务也依赖输入requirements/条款，不能独立充当标准权威来源。没有把 demo 素材复制到仓库或附件。

## 10. 本次实际验证与后续顺序

实际命令与证据：

1. `git rev-parse HEAD` / `git status --short`：确认上述基线且本代理取证时干净；结束再次检查。
2. `node --test web/src/views/graph/__tests__/graphLayout.test.mjs`：**23 passed，0 failed**，日志 `product-layout-tests.log`。覆盖布局基本边界与节点数量，不能排除PC-05/06/07，因为相关断言没有这些反例。
3. 在 `server/` 运行：

   ```sh
   KG_DATABASE_URL=sqlite:// PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q -p no:cacheprovider tests/test_m4_graph_analysis.py tests/test_m4_prop_constraints.py -k 'graph_diff or shortest_path or layout_recommendation or view_template or core_check or data_prop_constraint_fields_round_trip'
   ```

   **5 selected passed**（diff、path、推荐改名不变性、视图模板、属性字段往返），日志 `product-targeted-pytest.log`；有 Starlette/httpx/anyio 弃用警告。虽然过滤词含 core_check，所选两个测试文件没有该测试，**不把核心核对算成本次通过**。

4. 布局纯函数+真实 graphPaths 探针：schema/sankey/chord 可绘边均0/1；三节点环漏一个；供应链双角色列错。日志 `product-graph-probes.log`。可复跑：`node /private/tmp/knowledge-audit-20261106/product-graph-probes.mjs`。脚本直接导入当前仓库布局与渲染路径函数，输出观测结果，不把缺陷结果当成通过测试。
5. 内存 SQLite 图版本探针：相同IRI/SPO但属性/边属性/派生边变化，diff全0。日志 `product-diff-probe.log`。从 `server/` 可复跑：`KG_DATABASE_URL=sqlite:// PYTHONDONTWRITEBYTECODE=1 .venv/bin/python /private/tmp/knowledge-audit-20261106/product-diff-probe.py`。仅创建隔离内存数据，未访问真实知识库。
6. `sqlite3 -readonly samples/enterprise_demo.sqlite 'select name from sqlite_master where type="table" order by name;'`：17表；用于校准文档，未读取个人/真实业务行。

建议主代理按“先闭环、后结果正确、再扩展范围”的依赖次序修复，逐项定向验证后再推进：

1. 规则挂入 PC-01、发布后修订 PC-02、历史当前集切换 PC-11；补从UI真正触发这些后端动作的回归。
2. 增量字段无损 PC-03、资产分页 PC-08，避免表单编辑丢字段和大库不可选。
3. 图谱差异 PC-04/12、聚合边 PC-05、环路 PC-06、供应链 PC-07；现有测试补反例，继而在UI核验。
4. 版本证据跳转 PC-13 与业务审计 PC-14；和后端冻结/安全审计结论合并，避免重复或冲突修复。
5. M4导入 PC-09、核心核对 PC-10；明确保真范围后执行空库往返，不以解析成功替代恢复成功。
6. 视图语义配置 PC-15、融合解释 PC-16与其余G形态增强，依据产品范围决定批次；完整DL、周期调度、文档入图等仍按规划单独验收。

报告结构检查：37/37路由、32/32形态、62/62 V-*核验项均逐行覆盖；显式仓库路径存在性检查无缺失。最终HEAD仍为 `3e729e4213db3cd61a2430aa49962f226e65f312`，`git status --short` 为空。

本报告是产品覆盖子审计，供主代理合并工程、UI、前端并发和后端安全结论；不是全项目最终放行报告。
