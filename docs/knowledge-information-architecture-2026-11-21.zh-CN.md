# 知识中台信息架构与 GB/T 48000.3—2026 标准符合性改造方案

> 历史资料说明（2026-11-26补注）：本文保留原日期、基线和当时结论，不代表当前能力或本轮验收；当前入口见[文档中心](README.md)。

> 文档状态：**提案，待确认；本轮不实施。**
> 审计日期：2026-11-21
> 代码基线：`17de2e6`（2026-11-20）
> 工作区：`/Users/linyer/Public/Private/knowledge`
> 运行地址：`http://localhost:4010/`

## 0. 文档定位

本文件把“知识中台”的前端信息架构审计、GB/T 48000.3—2026 标准符合性核对、目标菜单结构、目标目录结构与分阶段迁移计划整理为一份可审阅、可验收、可实施的方案。

本轮审计本身是只读的，没有修改任何源码、路由、菜单或目录。本文件只记录：

- 当前事实与证据；
- 建议的目标结构；
- 分阶段迁移顺序；
- 每一步的验收条件；
- 需要用户确认的边界。

本文档不是实施授权。只有用户确认方案和需要变更的菜单、路由、文件边界后，才进入实施阶段。

## 1. 证据、结论标记与判定边界

### 1.1 证据标记

| 标记  | 含义                           |
| ----- | ------------------------------ |
| `[S]` | 已读取当前源码或配置           |
| `[R]` | 已在运行页面实际观察或操作     |
| `[D]` | 设计判断，不是国标或项目硬规则 |
| `[U]` | 未验证                         |

### 1.2 判定边界

GB/T 48000.3—2026 主要规定标准本体的建模要求，包括实体类型、数据属性、对象属性、公理规则、扩展方式、命名空间和元数据；它不直接规定后台菜单、路由或前端目录。

因此本方案分别评价四个维度，不混写为单一的“符合/不符合”：

- **C｜本体模型符合性**：实体、属性、关系、约束、版本和元数据是否覆盖国标要求。
- **F｜前端功能支撑**：用户能否通过页面完成建模、装配、发布、校验和追溯。
- **IA｜信息架构清晰度**：菜单、路由、页面、面包屑、搜索和返回路径是否形成一致任务链。
- **ARCH｜文件结构健康度**：页面、私有组件、共享组件、API和领域边界是否符合项目约定。

本文明确禁止以下推断：

- 存在一个页面，不等于国标符合；
- 目录整齐，不等于国标合规；
- 国标列出某个核心类，不等于必须新增一个一级菜单；
- README、设计稿或历史审计中的承诺，不等于当前实现；
- 静态路由存在，不等于浏览器操作已验证。

## 2. 一页结论

### 2.1 当前应用的实际产品边界

当前应用不是单纯的“标准文档管理后台”，而是覆盖以下业务面的知识中台：

1. **通用语义建模**：命名空间、实体类型、数据属性、关系类型、业务域、本体装配与发布。
2. **数据接入**：数据源、元数据快照、数据目录、样例预览。
3. **映射与抽取**：映射草稿、编译预览、映射发布、同步/异步抽取、运行报告。
4. **图谱与证据**：图谱浏览、实体详情、实体/事实/源行追溯、实例校验报告。
5. **知识库**：TXT/MD/CSV文档处理、关键词/语义/混合检索、抽取式回答、原文证据、人工图谱关联。
6. **治理与系统**：标准条款资料、规则、装配模板、版本冻结、RDF交换、账号、审计和AI模型配置。

当前应用已经拥有较完整的**通用建模和知识抽取平台**，但尚未随应用提供一套经过批准的 GB/T 48000.3 核心规范包。

### 2.2 当前菜单计数

| 口径               | EDITOR / VIEWER | ADMIN |
| ------------------ | --------------: | ----: |
| 源码 `NavGroup` 数 |               6 |     7 |
| 实际一级菜单节点   |               7 |     8 |
| 实际可展开分组     |               5 |     6 |
| 一级直接叶子       |               2 |     2 |
| 二级叶子           |              22 |    26 |
| 全部可见叶子       |              24 |    28 |

说明：

- “工作台”为独立一级叶子。
- “知识库”源码中是单子项分组，但渲染逻辑将其压缩为一级叶子。
- “系统管理”仅管理员生成。

### 2.3 核心任务链结论

| 任务链           | 当前结论 | 主要断点                                                                         |
| ---------------- | -------- | -------------------------------------------------------------------------------- |
| A 标准语义建模链 | 部分闭合 | 通用建模、装配和发布真实存在；标准核心模型和标准 Profile 未批准                  |
| B 数据接入链     | 基本闭合 | 数据源→目录→映射→发布存在；元数据快照是必要前置                                  |
| C 抽取与图谱链   | 部分闭合 | 任务和运行存在；运行摘要缺少直达结果集图谱，隔离明细无前端入口                   |
| D 治理链         | 部分闭合 | 规则、四态报告、历史、导出、导入存在；既有报告发现、报告导出UI和规则完整往返仍缺 |
| E 知识库链       | 部分闭合 | 上传→处理→检索→证据→人工关联存在；文档类型有限，自动文档入图链缺失               |

### 2.4 当前菜单的五个主要问题

1. **同一层混用对象、动作、输出、辅助配置和系统管理。**
2. **“知识库 / 知识追溯 / 图谱与追溯 / 校验报告”概念重叠。**
3. **“本体与资源”含8个叶子，横跨 `ontology/` 与 `governance/` 两个目录。**
4. **详情页面包屑丢失对象身份和详情层，只保留列表页高亮与列表名。**
5. **快捷搜索只索引菜单标签，不覆盖详情、账户、报告与部分隐藏工具。**

### 2.5 国标模型的主要缺口

1. **标准核心实体未作为一等模型提供**：当前只有通用实体类型能力。
2. **标准实体、标准化对象、相关方、领域类别、要素、层次、技术内容、制定程序没有固定 IRI、定义、属性和关系集合。**
3. **表1的34个核心对象属性没有标准化落地。**
4. **部分8.2核心规则缺失**：`owl:hasKey`、通用唯一元组、日期先后、替代链、无标题条结构限制等未形成完整闭环。
5. **带OWL/SHACL治理规则的本体无法通过完整恢复器无损往返。**

### 2.6 四个维度的最终结论

| 维度                  | 结论           | 理由摘要                                                                                                  |
| --------------------- | -------------- | --------------------------------------------------------------------------------------------------------- |
| **C｜本体模型符合性** | **部分符合**   | 通用模型、RDF/OWL/SHACL子集、版本冻结存在；6.2核心模型、核心对象属性、部分8.2规则和完整交换不成立         |
| **F｜前端功能支撑**   | **部分**       | 通用建模、发布、校验、抽取、图谱和知识库均有真实入口；标准Profile、报告发现、隔离明细和知识库自动入图缺失 |
| **IA｜菜单清晰度**    | **需要重构**   | 分类轴混合、语义重叠、详情面包屑丢失、隐藏能力可发现性不足                                                |
| **ARCH｜文件结构**    | **有语义漂移** | 页面大体按业务域组织，但菜单跨目录、页面身份落后、Designer越域导入graph私有工具                           |

### 2.7 验证状态

- **已验证 `[S]`**：当前源码、路由、菜单、i18n、页面文件、主要API模块、通用本体模型、验证四态、版本冻结、知识库与映射页面实现。
- **局部验证 `[R]`**：登录页桌面/窄屏渲染；未登录打开 `/ontology/designer` 与 `/graph/entities/...` 会跳转登录并携带 `redirect`；仓库隔离E2E管理员凭据登录失败并显示错误。
- **未验证 `[U]`**：登录后的真实菜单交互、真实数据、OCR/PDF文档、真实角色权限、真实API链、空态/错误态、既有报告发现、图谱与知识库完整浏览器闭环。
- **本轮未执行**：构建、全量测试、E2E、迁移、发布、真实 SHACL 往返、RDF/OWL工具互操作、生产数据库验证。

## 3. 当前基线

### 3.1 代码与运行基线

| 项目         | 基线                                     |
| ------------ | ---------------------------------------- |
| 仓库         | `/Users/linyer/Public/Private/knowledge` |
| HEAD         | `17de2e6`                                |
| 前端         | Vue 3 + Vite，源码在 `web/src/`          |
| 后端         | Python FastAPI，源码在 `server/app/`     |
| 运行地址     | `http://localhost:4010/`                 |
| 登录页       | 可访问 `[R]`                             |
| 运行深层页面 | 登录受阻止，未验证 `[U]`                 |

### 3.2 运行时观察

已完成以下只读观察：

- `/login` 返回登录页；
- 未登录访问 `/ontology/designer` 跳转至 `/login?redirect=/ontology/designer`；
- 未登录访问图谱实体深链同样保留 `redirect`；
- 使用仓库中隔离 E2E 管理员凭据登录失败，提示“账号或密码不正确”；
- 375px 登录页无横向页面溢出。

未做：

- 不猜测账号或密码；
- 不创建真实账号；
- 不写入项目数据库；
- 不将一次登录失败解释为应用不可用。

### 3.3 工作区说明

审计期间存在隔离设计原型，未纳入当时正式产品基线。正式设计后续已进入主前端，独立原型已于 2026-11-23 清理；迁移依据见 [正式设计迁移](./frontend-migration-2026-11-21.zh-CN.md)。

本文件写入后，工作区还会出现本文档本身以及审计前已存在的其他未跟踪改动；这些都不代表本轮改动了应用路由、菜单或页面。

## 4. 产品能力树

> 能力树先从页面、API和真实任务行为归纳，再映射到菜单。菜单不是产品能力的唯一来源。

### 4.1 L0–L3 能力树

| L0       | L1 业务能力域 | L2 用户任务    | L3 页面/操作                                             | 当前入口                                   | 前置条件与下一步                    | 证据 |
| -------- | ------------- | -------------- | -------------------------------------------------------- | ------------------------------------------ | ----------------------------------- | ---- |
| 知识中台 | 工作台        | 启动作业       | 工作台总览、当前结果集、资产计数、继续工作               | `dashboard`                                | 登录 → 建模/数据/抽取/图谱          | [S]  |
| 知识中台 | 标准语义资产  | 管理命名空间   | 登记、查看、保护状态、使用中阻断删除                     | `namespaces`                               | 有命名空间 → 建类型                 | [S]  |
| 知识中台 | 标准语义资产  | 管理实体类型   | 创建、详情、数据属性、父类、改名、发布、撤回             | `entity-types`、`entity-detail`            | 命名空间 → 草稿属性 → 发布          | [S]  |
| 知识中台 | 标准语义资产  | 管理关系类型   | 端点、基数、逆关系、OWL特征、关联实体、发布、撤回        | `relation-types`、`relation-detail`        | 已有实体类型 → 端点 → 发布          | [S]  |
| 知识中台 | 标准语义资产  | 组织业务域     | 域树、成员、跨域引用、发布检查、发布                     | `domains`                                  | 类型/关系存在 → 域成员 → 发布       | [S]  |
| 知识中台 | 标准语义资产  | 维护枚举与模板 | 枚举版本、引用、模板创建/复制/实例化、核心资源核对       | `enum-dictionaries`、`assembly-templates`  | 已发布资源 → 枚举/模板 → 装配       | [S]  |
| 知识中台 | 本体装配      | 创建和发布本体 | 本体库、引用装配、冲突检查、发布、历史                   | `ontologies`                               | 已发布资源/域 → 装配 → 校验 → 发布  | [S]  |
| 知识中台 | 本体装配      | 画布建模       | 资源池、布局、检查器、规则选择、校验、发布、冻结版本查看 | `designer`                                 | 本体草稿 → 装配 → 校验 → 发布       | [S]  |
| 知识中台 | 本体装配      | AI辅助建模     | 类型补全、候选建模、人工确认后写入草稿                   | `designer`内工具                           | 草稿、模型配置、授权材料 → 更新草稿 | [S]  |
| 知识中台 | 数据接入      | 建数据源       | 创建、测试、编辑、状态、删除                             | `datasources`                              | A/E角色 → 连接 → 测试成功           | [S]  |
| 知识中台 | 数据接入      | 查看元数据     | 采集快照、结构树、差异、引用                             | `data-catalog`                             | 连接成功 → 采集 → 查看结构          | [S]  |
| 知识中台 | 数据接入      | 预览样例       | 受限表/字段预览、返回目录                                | `sample-preview`                           | 数据源可用 → 查询 → 返回目录        | [S]  |
| 知识中台 | 映射与抽取    | 创建映射       | 实体/关系映射、字段转换、编译预览、保存草稿、发布        | `mapping-wizard`                           | 已发布本体、数据源、目录 → 发布映射 | [S]  |
| 知识中台 | 映射与抽取    | 执行任务       | 创建抽取任务、取消、调度、看进度                         | `extraction-tasks`                         | 已发布映射、数据源 → 运行           | [S]  |
| 知识中台 | 映射与抽取    | 查看运行       | 运行列表、摘要、版本链、下载                             | `extraction-runs`                          | 运行记录 → 摘要/下载                | [S]  |
| 知识中台 | 映射与抽取    | 文本事实抽取   | 选择本体、粘贴文本、建议、人工确认                       | `ai-assist`                                | 模型可用 → 建议 → 确认              | [S]  |
| 知识中台 | 图谱与证据    | 浏览图谱       | 中心展开、布局、路径、差异、矩阵、中心性、历史           | `graph-browse`                             | 有结果集 → 浏览 → 证据              | [S]  |
| 知识中台 | 图谱与证据    | 查看实例       | 实体列表、实体详情、360视图、融合证据                    | `graph-entities`、`graph-entity-detail`    | 有结果集 → 搜索 → 详情              | [S]  |
| 知识中台 | 图谱与证据    | 追溯证据       | 实体/事实/源行反查、冻结规则与来源链                     | `graph-evidence`                           | 有结果集 → IRI/三元组/源行 → 证据链 | [S]  |
| 知识中台 | 图谱与证据    | 校验实例       | 选结果集、运行校验、四态汇总、结果筛选                   | `graph-reports`                            | A/E角色 → 运行 → 看结果             | [S]  |
| 知识中台 | 图谱与证据    | 处理隔离       | 隔离明细、字段、理由、来源行                             | 缺失前端入口                               | 运行记录 → 隔离明细                 | [S]  |
| 知识中台 | 知识库        | 管理知识库     | 创建、编辑、归档/恢复、共享声明                          | `knowledge-bases`、`knowledge-base-detail` | A/E角色 → 建库                      | [S]  |
| 知识中台 | 知识库        | 处理文档       | TXT/MD/CSV上传、重复检测、任务、下载、重处理             | 知识库详情及文档抽屉                       | 未归档、worker可用 → 上传 → 处理    | [S]  |
| 知识中台 | 知识库        | 检索和回答     | 关键词/语义/混合检索、抽取式回答、引用                   | `knowledge-base-search`                    | 文档可检索、模型配置可用 → 证据     | [S]  |
| 知识中台 | 知识库        | 关联图谱       | 从原文证据人工关联实体或事实、查看反向知识引用           | 知识证据抽屉、图谱侧引用组件               | 可写、有效结果集 → 关联             | [S]  |
| 知识中台 | 治理与交换    | 维护条款和规则 | 条款资料、OWL/SHACL/DATA/DERIVATION规则、正反例测试      | `governance-clauses`、`governance-rules`   | 条款 → 规则 → 本体装配              | [S]  |
| 知识中台 | 治理与交换    | 导出与恢复     | 历史修订、Turtle/JSON-LD导出、导入预览、完整恢复         | `ontology-export`                          | 已发布本体 → 导出；A/E角色 → 导入   | [S]  |
| 知识中台 | 系统管理      | 管理账号与AI   | 用户、角色能力说明、操作审计、AI模型配置                 | `system-*`                                 | ADMIN → 管理                        | [S]  |

### 4.2 特别能力检查

| 能力                                     | 真实入口                     | 能力属性            | 当前问题                                      |
| ---------------------------------------- | ---------------------------- | ------------------- | --------------------------------------------- |
| 命名空间登记                             | `本体与资源 → 命名空间`      | 建模配置            | 在业务资产组中和类型库并列，层级偏高          |
| 实体类型创建、编辑、继承、发布           | 实体类型库与详情             | 资产列表+详情       | 详情隐藏合理，但面包屑只有列表层              |
| 关系类型创建、定义域、值域、基数、逆关系 | 关系类型库与详情             | 资产列表+详情       | 逆关系可选；标准核心关系集未提供              |
| 业务域组织                               | 业务域页                     | 资产维护            | `BusinessDomain`不能自动等同国标领域类别      |
| 本体装配、校验、发布、冻结               | 本体库、本体设计器           | 工作台              | 校验结果明细和既有报告入口不足                |
| 数据源连接                               | 数据源页                     | 连接资产            | 远端真实连接未验证                            |
| 数据目录、结构预览                       | 数据目录、样例预览           | 资产工作台+工具     | 样例预览作为固定菜单叶子偏重                  |
| 映射配置                                 | 映射向导                     | 多步工作台          | “向导”实际承载长期管理，不只是单次向导        |
| 抽取任务和运行                           | 抽取任务、抽取运行           | 操作+结果           | 运行摘要无直接图谱入口                        |
| 图谱浏览、实体详情、证据追溯             | 图谱浏览、实体实例、知识追溯 | 结果工作台+证据工具 | 术语和菜单重叠                                |
| 校验报告四态                             | 图谱校验报告、设计器内面板   | 工具+详情           | 没有既有报告发现；VIEWER不能查看历史报告入口  |
| 版本历史、导出、导入、恢复               | 版本与交换                   | 工作台              | route/name/file 仍为 `ontology-export/export` |
| 标准条款、规则、装配模板                 | 条款、规则、模板             | 资产+工具           | 条款与规则没有结构化引用                      |
| 知识库检索与图谱证据                     | 知识库检索、知识追溯         | 两个领域            | 人工关联和自动来源链语义必须区分              |

## 5. 当前菜单树

### 5.1 菜单表

| 层级 | 显示名      | route name           | 路径                            | 页面文件                                         | 可见角色 | 性质          | 主要问题                         |
| ---: | ----------- | -------------------- | ------------------------------- | ------------------------------------------------ | -------- | ------------- | -------------------------------- |
|    1 | 工作台      | `dashboard`          | `/`                             | `web/src/views/Dashboard.vue`                    | 全登录   | 一级目的地    | 流程卡没有独立知识库阶段         |
|    1 | 知识库      | `knowledge-bases`    | `/knowledge-bases`              | `web/src/views/knowledge/KnowledgeBases.vue`     | 全登录   | 一级目的地    | 源码单子项组视觉上被压缩         |
|    1 | 本体与资源  | —                    | —                               | —                                                | 全登录   | 分组          | 混合对象、工作台、配置和模板     |
|    2 | 本体库      | `ontologies`         | `/ontology/ontologies`          | `web/src/views/ontology/Ontologies.vue`          | 全登录   | 资产列表      | 与设计器边界需标签化             |
|    2 | 本体设计器  | `designer`           | `/ontology/designer`            | `web/src/views/ontology/Designer.vue`            | 全登录   | 全屏工作台    | 不是普通列表目的地               |
|    2 | 实体类型库  | `entity-types`       | `/ontology/entity-types`        | `web/src/views/ontology/EntityTypes.vue`         | 全登录   | 资产列表      | 详情隐藏                         |
|    2 | 关系类型库  | `relation-types`     | `/ontology/relation-types`      | `web/src/views/ontology/RelationTypes.vue`       | 全登录   | 资产列表      | 详情隐藏                         |
|    2 | 业务域      | `domains`            | `/ontology/domains`             | `web/src/views/ontology/Domains.vue`             | 全登录   | 资产维护      | 与国标领域类别概念不可混称       |
|    2 | 命名空间    | `namespaces`         | `/ontology/namespaces`          | `web/src/views/ontology/Namespaces.vue`          | 全登录   | 建模配置      | 高频前置配置与资产并列           |
|    2 | 枚举词典    | `enum-dictionaries`  | `/governance/enum-dictionaries` | `web/src/views/governance/EnumDictionaries.vue`  | 全登录   | 版本化配置    | 菜单/路由/文件归属不一致         |
|    2 | 装配模板    | `assembly-templates` | `/governance/templates`         | `web/src/views/governance/AssemblyTemplates.vue` | 全登录   | 模板资产+工具 | 菜单/路由/文件归属不一致         |
|    1 | 数据接入    | —                    | —                               | —                                                | 全登录   | 分组          | 三个入口主题清楚，样例是工具     |
|    2 | 数据源      | `datasources`        | `/datasources`                  | `web/src/views/datasources/DataSources.vue`      | 全登录   | 连接资产      | 测试/编辑另受角色门控            |
|    2 | 数据目录    | `data-catalog`       | `/datasources/catalog`          | `web/src/views/datasources/DataCatalog.vue`      | 全登录   | 资产工作台    | 与元数据快照职责对应             |
|    2 | 样例预览    | `sample-preview`     | `/datasources/preview`          | `web/src/views/datasources/SamplePreview.vue`    | 全登录   | 上下文工具    | 不应长期作为固定一级组叶子       |
|    1 | 映射与抽取  | —                    | —                               | —                                                | 全登录   | 分组          | “向导”承载多个长期能力           |
|    2 | 映射向导    | `mapping-wizard`     | `/extraction`                   | `web/src/views/extraction/MappingWizard.vue`     | 全登录   | 工作台        | 不是一次性的向导                 |
|    2 | AI 助手     | `ai-assist`          | `/extraction/ai-assist`         | `web/src/views/extraction/AiAssist.vue`          | 全登录   | 工具页        | 名称泛化，实际是文本事实抽取     |
|    2 | 抽取任务    | `extraction-tasks`   | `/extraction/tasks`             | `web/src/views/extraction/ExtractionTasks.vue`   | 全登录   | 工作流操作    | 与运行列表拆分合理               |
|    2 | 抽取运行    | `extraction-runs`    | `/extraction/runs`              | `web/src/views/extraction/ExtractionRuns.vue`    | 全登录   | 运行结果      | 无独立详情，无直接看图谱         |
|    1 | 图谱与追溯  | —                    | —                               | —                                                | 全登录   | 分组          | “追溯”与知识库“证据”语义重叠     |
|    2 | 图谱浏览    | `graph-browse`       | `/graph`                        | `web/src/views/graph/GraphBrowse.vue`            | 全登录   | 全屏工作台    | 多个内部工具共享同一路由         |
|    2 | 实体实例    | `graph-entities`     | `/graph/entities`               | `web/src/views/graph/GraphEntities.vue`          | 全登录   | 实例列表      | 实例详情隐藏                     |
|    2 | 知识追溯    | `graph-evidence`     | `/graph/evidence`               | `web/src/views/graph/GraphEvidence.vue`          | 全登录   | 证据工具      | 与知识库证据抽屉重叠             |
|    2 | 校验报告    | `graph-reports`      | `/graph/reports`                | `web/src/views/graph/GraphReports.vue`           | 全登录   | 工具+结果     | 无既有报告载入，标题与菜单不一致 |
|    1 | 治理与版本  | —                    | —                               | —                                                | 全登录   | 分组          | 枚举/模板不在本组                |
|    2 | 规则库      | `governance-rules`   | `/governance/rules`             | `web/src/views/governance/GovernanceRules.vue`   | 全登录   | 规则资产      | 条款关系未结构化                 |
|    2 | 标准条款    | `governance-clauses` | `/governance/clauses`           | `web/src/views/governance/StandardClauses.vue`   | 全登录   | 资料资产      | 不是完整标准实体                 |
|    2 | 版本与交换  | `ontology-export`    | `/governance/export`            | `web/src/views/governance/OntologyExport.vue`    | 全登录   | 工作流工具    | route/file 仍以 export 命名      |
|    1 | 系统管理    | —                    | —                               | —                                                | ADMIN    | 分组          | 角色页只读                       |
|    2 | 用户管理    | `system-users`       | `/system/users`                 | `web/src/views/system/Users.vue`                 | ADMIN    | 管理入口      | 角色分配在用户页                 |
|    2 | 角色管理    | `system-roles`       | `/system/roles`                 | `web/src/views/system/Roles.vue`                 | ADMIN    | 能力说明      | 名称像 CRUD，实际只读            |
|    2 | 操作日志    | `system-audit-logs`  | `/system/audit-logs`            | `web/src/views/system/AuditLogs.vue`             | ADMIN    | 审计入口      | 账户与资产业务审计混页           |
|    2 | AI 模型配置 | `system-ai-models`   | `/system/ai-models`             | `web/src/views/system/AiModels.vue`              | ADMIN    | 系统配置      | 是基础配置，不是业务 AI 入口     |

### 5.2 菜单关键问题的明确回答

1. **当前一级菜单数**：普通角色 7 个，管理员 8 个。
2. **单子项伪装一级分组**：源码存在“知识库”单子项组，但实际渲染为一级叶子；当前没有可见的单子项包装。
3. **同层分类轴混合**：存在。“本体与资源”混合对象/工作台/配置/模板；“图谱与追溯”混合输出/实例/证据/校验。
4. **相近名称职责不清**：存在。“知识库”“知识追溯”“图谱与追溯”“证据”是不同资产或动作，但语义接近，需要层级化。
5. **叶子过多**：“本体与资源”有8个叶子，需要二级分组；其余多数业务组4个叶子可以接受。
6. **业务标签实际是配置/工具**：存在。“样例预览”“AI 助手”“版本与交换”“本体设计器”不是普通资产列表。
7. **详情页是否进菜单**：不建议。详情页继续从列表/图谱进入；需要补“对象层”面包屑、返回路径和上下文保留。
8. **隐藏项权限一致性**：系统管理隐藏与 `adminOnly` 一致；页面内写操作由 A/E 控件门控和后端写操作鉴权共同控制。但角色能力说明与实际测试按钮仍存在冲突。

## 6. 路由—页面—文件矩阵

> 详细路由矩阵以“页面身份”为主。目录归属是当前事实；目标归属见第12节的新目录结构。

| 路由 name               | 路径                            | 当前页面                                  | 当前业务目录 | API 模块                                                        | 菜单暴露     | 详情回退          | 权限                 | 备注                                   |
| ----------------------- | ------------------------------- | ----------------------------------------- | ------------ | --------------------------------------------------------------- | ------------ | ----------------- | -------------------- | -------------------------------------- |
| `dashboard`             | `/`                             | `views/Dashboard.vue`                     | 根views      | `dashboard.ts`                                                  | 一级叶子     | —                 | 全登录               | 总览                                   |
| `knowledge-bases`       | `/knowledge-bases`              | `views/knowledge/KnowledgeBases.vue`      | knowledge    | `knowledge.ts`                                                  | 一级叶子     | —                 | 全登录；写 A/E       | 知识库列表                             |
| `knowledge-base-detail` | `/knowledge-bases/:id`          | `views/knowledge/KnowledgeBaseDetail.vue` | knowledge    | `knowledge.ts`                                                  | 隐藏         | `knowledge-bases` | 全登录；写 A/E       | 库名作标题                             |
| `knowledge-base-search` | `/knowledge-bases/:id/search`   | `views/knowledge/KnowledgeSearch.vue`     | knowledge    | `knowledge.ts`、`graph.ts`                                      | 隐藏         | `knowledge-bases` | 全登录               | 能力受模型配置门控                     |
| `ontologies`            | `/ontology/ontologies`          | `views/ontology/Ontologies.vue`           | ontology     | `ontology.ts`                                                   | 本体与资源组 | —                 | 全登录；写 A/E       | 新建后进 Designer                      |
| `namespaces`            | `/ontology/namespaces`          | `views/ontology/Namespaces.vue`           | ontology     | `namespaces.ts`                                                 | 本体与资源组 | —                 | 全登录；写 A/E       | 被引用/受保护不可删                    |
| `entity-types`          | `/ontology/entity-types`        | `views/ontology/EntityTypes.vue`          | ontology     | `entity-types.ts`、`domains.ts`                                 | 本体与资源组 | —                 | 全登录；写 A/E       | 详情入口                               |
| `entity-detail`         | `/ontology/entity-types/:id`    | `views/ontology/EntityDetail.vue`         | ontology     | `entity-types.ts`                                               | 隐藏         | `entity-types`    | 全登录；写 A/E       | 面包屑仅到列表                         |
| `relation-types`        | `/ontology/relation-types`      | `views/ontology/RelationTypes.vue`        | ontology     | `relations.ts`、`entity-types.ts`                               | 本体与资源组 | —                 | 全登录；写 A/E       | 详情入口                               |
| `relation-detail`       | `/ontology/relation-types/:id`  | `views/ontology/RelationDetail.vue`       | ontology     | `relations.ts`                                                  | 隐藏         | `relation-types`  | 全登录；写 A/E       | 面包屑仅到列表                         |
| `domains`               | `/ontology/domains`             | `views/ontology/Domains.vue`              | ontology     | `domains.ts`、`entity-types.ts`、`relations.ts`                 | 本体与资源组 | —                 | 全登录；写 A/E       | 当前页内详情                           |
| `designer`              | `/ontology/designer`            | `views/ontology/Designer.vue`             | ontology     | `ontology.ts`、`validation.ts`、`domains.ts`、`relations.ts`    | 本体与资源组 | —                 | 全登录；写 A/E       | 全屏工作台；`?ontology=`只在挂载时读取 |
| `datasources`           | `/datasources`                  | `views/datasources/DataSources.vue`       | datasources  | `datasources.ts`                                                | 数据接入组   | —                 | 全登录；写 A/E       | 连接测试受限                           |
| `data-catalog`          | `/datasources/catalog`          | `views/datasources/DataCatalog.vue`       | datasources  | `datasources.ts`                                                | 数据接入组   | —                 | 全登录；采集 A/E     | 元数据快照                             |
| `sample-preview`        | `/datasources/preview`          | `views/datasources/SamplePreview.vue`     | datasources  | `datasources.ts`                                                | 数据接入组   | —                 | 全登录               | 工具页                                 |
| `mapping-wizard`        | `/extraction`                   | `views/extraction/MappingWizard.vue`      | extraction   | `mappings.ts`、`extraction.ts`、`datasources.ts`、`ontology.ts` | 映射与抽取组 | —                 | 全登录；写 A/E       | 多步工作台                             |
| `extraction-runs`       | `/extraction/runs`              | `views/extraction/ExtractionRuns.vue`     | extraction   | `extraction.ts`                                                 | 映射与抽取组 | —                 | 全登录               | 抽屉详情                               |
| `extraction-tasks`      | `/extraction/tasks`             | `views/extraction/ExtractionTasks.vue`    | extraction   | `extraction.ts`、`mappings.ts`                                  | 映射与抽取组 | —                 | 全登录；写 A/E       | 任务→运行                              |
| `ai-assist`             | `/extraction/ai-assist`         | `views/extraction/AiAssist.vue`           | extraction   | `ai.ts`、`ontology.ts`                                          | 映射与抽取组 | —                 | 全登录；写 A/E       | 文本抽取建议                           |
| `graph-browse`          | `/graph`                        | `views/graph/GraphBrowse.vue`             | graph        | `graph.ts`、`knowledge.ts`                                      | 图谱与追溯组 | —                 | 全登录               | 全屏工作台                             |
| `graph-entities`        | `/graph/entities`               | `views/graph/GraphEntities.vue`           | graph        | `graph.ts`                                                      | 图谱与追溯组 | —                 | 全登录               | 实例列表                               |
| `graph-entity-detail`   | `/graph/entities/:id`           | `views/graph/GraphEntityDetail.vue`       | graph        | `graph.ts`                                                      | 隐藏         | `graph-entities`  | 全登录               | `id` 是 IRI                            |
| `graph-evidence`        | `/graph/evidence`               | `views/graph/GraphEvidence.vue`           | graph        | `graph.ts`、`mappings.ts`                                       | 图谱与追溯组 | —                 | 全登录               | 实体/事实/源行                         |
| `graph-reports`         | `/graph/reports`                | `views/graph/GraphReports.vue`            | graph        | `validation.ts`                                                 | 图谱与追溯组 | —                 | 全登录；发起校验 A/E | 既有报告入口缺失                       |
| `governance-rules`      | `/governance/rules`             | `views/governance/GovernanceRules.vue`    | governance   | `governance.ts`                                                 | 治理与版本组 | —                 | 全登录；写 A/E       | 规则                                   |
| `governance-clauses`    | `/governance/clauses`           | `views/governance/StandardClauses.vue`    | governance   | `clauses.ts`                                                    | 治理与版本组 | —                 | 全登录；写 A/E       | 条款资料                               |
| `enum-dictionaries`     | `/governance/enum-dictionaries` | `views/governance/EnumDictionaries.vue`   | governance   | `enum-dictionaries.ts`                                          | 本体与资源组 | —                 | 全登录；写 A/E       | 归属漂移                               |
| `assembly-templates`    | `/governance/templates`         | `views/governance/AssemblyTemplates.vue`  | governance   | `templates.ts`、`clauses.ts`                                    | 本体与资源组 | —                 | 全登录；写 A/E       | 归属漂移                               |
| `ontology-export`       | `/governance/export`            | `views/governance/OntologyExport.vue`     | governance   | `ontology.ts`、`ontology-history.ts`、`ontology-restore.ts`     | 治理与版本组 | —                 | 全登录；导入 A/E     | 实为版本与交换                         |
| `account-profile`       | `/account/profile`              | `views/account/Profile.vue`               | account      | `auth.ts`                                                       | 用户下拉     | —                 | 全登录               | 本人资料                               |
| `account-security`      | `/account/security`             | `views/account/Security.vue`              | account      | `auth.ts`                                                       | 用户下拉     | —                 | 全登录               | 本人密码                               |
| `system-users`          | `/system/users`                 | `views/system/Users.vue`                  | system       | `auth.ts`                                                       | 系统管理组   | —                 | ADMIN                | 用户与角色分配                         |
| `system-roles`          | `/system/roles`                 | `views/system/Roles.vue`                  | system       | `auth.ts`                                                       | 系统管理组   | —                 | ADMIN                | 只读说明                               |
| `system-audit-logs`     | `/system/audit-logs`            | `views/system/AuditLogs.vue`              | system       | `auth.ts`、`asset-audit.ts`                                     | 系统管理组   | —                 | ADMIN                | 两类审计                               |
| `system-ai-models`      | `/system/ai-models`             | `views/system/AiModels.vue`               | system       | `ai-models.ts`                                                  | 系统管理组   | —                 | ADMIN                | 模型配置                               |
| `login`                 | `/login`                        | `views/auth/Login.vue`                    | auth         | `auth.ts`                                                       | 隐藏         | —                 | 公开                 | 已登录访问回工作台                     |
| `register`              | `/register`                     | `views/auth/Register.vue`                 | auth         | `auth.ts`                                                       | 隐藏         | —                 | 公开                 | 后端配置决定开放                       |
| `forgot-password`       | `/forgot-password`              | `views/auth/ForgotPassword.vue`           | auth         | `auth.ts`                                                       | 隐藏         | —                 | 公开                 | 找回能力可变                           |
| `reset-password`        | `/reset-password`               | `views/auth/ResetPassword.vue`            | auth         | `auth.ts`                                                       | 隐藏         | —                 | 公开                 | Token入口                              |
| `forbidden`             | `/forbidden`                    | `views/Forbidden.vue`                     | 根views      | `auth.ts`                                                       | 隐藏         | `dashboard`       | 全登录               | 面包屑为空                             |
| `not-found`             | `/:pathMatch(.*)*`              | `views/NotFound.vue`                      | 根views      | —                                                               | 隐藏         | `dashboard`       | 未标记公开           | 未登录深链先走登录                     |

### 6.1 已识别的结构漂移

| 漂移                                | 当前事实                                                   | 影响                                   |
| ----------------------------------- | ---------------------------------------------------------- | -------------------------------------- |
| 菜单与目录归属不一致                | 枚举、模板在“本体与资源”，路由/页面在 `governance/`        | 用户和开发对业务域理解不同             |
| 页面身份落后                        | `ontology-export` 实际包含版本历史、导出、导入、恢复       | 标签、深链和面包屑不能表达任务         |
| 跨域私有耦合                        | `Designer.vue` 导入 `views/graph/components/graphViewport` | graph 私有实现变更会牵动 ontology 页面 |
| 详情面包屑不显示对象                | `detailFallback` 只返回列表 route                          | 详情页无法看出当前实体、关系或知识库   |
| `meta.title` 未形成统一页面标题机制 | 只有知识库三页声明 `meta.title`，导航不消费                | 浏览器多标签、刷新和前进后退不准确     |
| 运行摘要不直达结果集                | 摘要显示图谱版本/发布清单，但无结果集图谱链接              | 抽取链需要绕行                         |
| 隐藏能力发现弱                      | QuickSearch 只搜菜单标签                                   | 报告、账户、详情页无法从快捷搜索直达   |

## 7. 核心任务链走查

### 7.1 A｜标准语义建模链

**当前入口**：`本体与资源 → 命名空间 / 实体类型库 / 关系类型库 / 业务域 / 本体库 / 本体设计器`

**最短路径**：

1. 命名空间 → 登记命名空间；
2. 实体类型库 → 新建 → 选择命名空间 → 保存；
3. 实体类型详情 → 添加数据属性、父类、约束 → 发布；
4. 关系类型库 → 新建 → 定义域/值域、基数、逆关系、OWL特征 → 发布；
5. 业务域 → 新建 → 加成员 → 发布检查 → 发布；
6. 本体库 → 新建/打开指定本体 → 本体设计器；
7. 装配资源、添加规则 → 运行校验 → 查看四态 → 发布；
8. 版本与交换 → 查看冻结内容/导出。

**前置条件**：A/E写权限、命名空间存在、引用资源已发布、域成员有效、本体草稿、服务端校验可用。

**空态/错误态/权限不足态**：

- 空命名空间有“登记”入口，并支持在实体/关系创建抽屉中就地登记；
- 设计器有catalog/load/action/save/validation/history多类错误提示；
- VIEWER只读，不能编辑或发布；
- 发布会在冻结输入上重新校验，不能只依赖之前显示的校验报告。

**断点**：

- 通用链路成立，但“标准核心模型”没有闭环；
- `Designer` 只展示检查码、状态和消息，不展示每项 `detail/rule_id/binding` 的完整来源；
- 设计器选择器切换本体不更新 URL，刷新或复制深链可能回到旧本体。

**国标相关能力是否暴露**：通用实体、属性、关系、定义域/值域、基数、逆关系、版本冻结可见；6.2核心类和8.2标准规则没有专门Profile。

### 7.2 B｜数据接入链

**当前入口**：`数据接入 → 数据源 → 数据目录 → 映射向导`

**最短路径**：

1. 数据源 → 新建 → 测试连接 → 保存；
2. 数据目录 → 选择数据源 → 采集元数据快照；
3. 查看结构树、差异、表引用；需要时进入样例预览；
4. 映射向导 → 选择本体/数据源/表 → 配置实体与关系映射；
5. 保存草稿 → 编译预览 → 处理预览错误 → 发布映射；
6. 运行已发布映射。

**前置条件**：A/E角色、连接可用、元数据快照存在、本体已发布、映射字段完整、编译预览清洁。

**空态/错误态/权限不足态**：

- 数据源有连接失败提示、连接测试失效和编辑抽屉；
- 数据目录有“无快照”错误和采集动作；
- 映射向导编译成功后才进入步骤4；发布要求当前预览清洁；
- VIEWER可查看但不可修改。

**断点**：

- 映射发布后到“开始运行→查看本轮图谱”仍被拆成多个页面；
- 数据目录与映射向导之间的数据上下文不能一步直达。

### 7.3 C｜抽取与图谱链

**当前入口**：`映射向导 → 开始运行` 或 `抽取任务 → 运行记录 → 图谱浏览`

**最短路径**：

1. 已发布映射；
2. 映射向导开始运行，或创建异步抽取任务；
3. 抽取运行 → 打开摘要；
4. 查看版本链、发布结果、统计和下载；
5. 进入图谱浏览 → 历史 → 选择结果集 → 设为当前；
6. 选择节点/边 → 实体详情或知识追溯 → 来源行/字段/转换/运行/冻结版本；
7. 需要质量治理时进入校验报告。

**前置条件**：已发布映射和本体、数据源可达、worker可用、有有效结果集；设当前要求可发布运行；A/E角色才可切换当前。

**空态/错误态/权限不足态**：

- 运行列表无数据为空态；
- 失败/取消运行明确提示“结果受保护”；
- 图谱页错误时保留已有数据并提示刷新；
- 切换当前只对可发布历史运行开放；
- VIEWER可看图，不可切换当前或保存视图模板。

**断点**：

- 运行摘要没有直接“查看本次结果集图谱”；
- `runQuarantine` API已在前端声明，但没有调用点；
- 图谱证据页只显示隔离数量警告，不能下钻隔离明细。

### 7.4 D｜治理链

**当前入口**：`治理与版本 → 标准条款 / 规则库 / 版本与交换`

**最短路径**：

1. 标准条款 → 建条款资料；
2. 规则库 → 新建规则 → 来源、目标IRI、语言、表达式、正反例 → 保存 → 测试；
3. 本体设计器 → 装配规则 → 运行校验；
4. 查看四态 → 发布；
5. 版本与交换 → 选择修订 → 导出 Turtle/JSON-LD；
6. 导入预览 → 解决冲突 → 恢复为新本体；
7. 查看历史冻结资源/规则。

**前置条件**：条款/规则可写、本体草稿、规则可执行或明确 NOT_RUN、已发布本体可导出、导入内容受大小和语义支持限制。

**空态/错误态/权限不足态**：

- 设计器和报告页均展示四态；
- 规则测试返回 NOT_RUN 时显示“未执行”，不显示通过；
- 导入预览列出冲突/不支持三元组并阻断应用；
- VIEWER可查看，但不能导入或编辑。

**断点**：

- 条款与规则只有自由文本来源，没有结构化条款 ID 关系；
- `all_core_present` 仅核对名称与资源种类，响应明确 `REQUESTED_NAME_KIND_ONLY` 和 `standards_conformance=NOT_RUN`；
- 带 OWL/SHACL `ruleSnapshot` 的本体导出后不能通过完整恢复器；
- 校验报告导出 API 存在，前端无下载入口。

### 7.5 E｜知识库链

**当前入口**：`知识库 → 知识库详情 → 文档 → 检索`

**最短路径**：

1. 知识库 → 新建；
2. 详情页上传 TXT/MD/CSV；
3. 查看文档处理任务、失败/部分状态和重处理；
4. 进入检索 → 输入查询 → 选择关键词/语义/混合、搜索/回答；
5. 打开命中片段 → 原文证据、行/段定位、处理代次；
6. A/E角色将证据人工关联到已有图谱实体/事实；
7. 图谱侧反向查看知识库引用。

**前置条件**：知识库未归档、格式/大小受限、处理 worker 可用、关键词检索可用；语义/回答依赖模型配置；人工关联需要有效结果集、可写文档修订。

**空态/错误态/权限不足态**：

- 知识库列表有空态和无结果态；
- 详情有处理中轮询暂停提示；
- 文档抽屉展示索引、任务、失败/部分、重处理、归档；
- 检索能力缺失时禁用语义/回答并显示配置提示；
- 证据抽屉对历史/归档文档禁止新增关联。

**断点**：

- 当前仅支持 `.txt/.md/.csv`，PDF/DOCX/标准结构化文档不在入口；
- 证据到图谱是人工关联，不等于自动抽取来源；
- “文档→标准条款/术语/信息单元→本体”的产品链没有自动入口。

## 8. GB/T 48000.3—2026 能力映射

### 8.1 条款索引

| 条款        | 主题                              | PDF/正文页码 |
| ----------- | --------------------------------- | ------------ |
| 5.1         | 建模基本要求                      | 8/2          |
| 5.2         | 本体核心组成                      | 9/3          |
| 5.3         | 形式化要求                        | 9/3          |
| 5.4.1–5.4.3 | 命名空间与 IRI                    | 9/3          |
| 6.1.1–6.1.3 | 实体类型确定原则                  | 9–10/3–4     |
| 6.2.1–6.2.6 | 核心实体类型                      | 10–14/4–8    |
| 6.3.1–6.3.2 | 版本类、文件编号类                | 14/8         |
| 7.1–7.3     | 通用属性、数据属性、对象属性、表1 | 14–16/8–10   |
| 8.1–8.2     | 公理与核心规则                    | 16–17/10–11  |
| 9.1–9.2     | 扩展范围和原则                    | 17/11        |
| A.1–A.3     | 实体/属性元数据、基本数据类型     | 18–19/12–13  |

### 8.2 覆盖映射

> `DIRECT` 只表示当前模型或页面直接表达了该要求，不表示完整标准认证；`GENERIC` 表示只有通用机制，没有标准语义；`MISSING` 表示没有可验证能力；`NO_UI` 表示属于模型、序列化、推理或校验，不需单独页面。

| 国标条款        | 要求摘要                                                 | 当前模型/数据能力                              | 当前页面或操作           | 状态    | 缺口                                            |
| --------------- | -------------------------------------------------------- | ---------------------------------------------- | ------------------------ | ------- | ----------------------------------------------- |
| 5.1             | 语义与结构兼顾；要素内容与表述形式分开；跨域共享         | 通用实体/关系；可自定义结构                    | 类型、属性、关系编辑     | GENERIC | 无标准“信息单元/表述形式”专用类                 |
| 5.2             | 实体类型、数据属性、对象属性、公理                       | 资源类型、属性、关系、规则                     | 类型、关系、规则、设计器 | DIRECT  | 标准核心语义需专门Profile                       |
| 5.3             | RDF/RDFS/OWL；Turtle/JSON-LD；SHACL                      | RDF/OWL子集、Turtle/JSON-LD、pySHACL           | 版本与交换、规则测试     | DIRECT  | 复杂OWL、规则完整恢复、标准SHACL报告仍受限      |
| 5.4             | 命名空间、全球唯一IRI                                    | Namespace注册、IRI生成、唯一约束               | 命名空间、类型/关系创建  | DIRECT  | 核心资源保护不完全；名称跨命名空间全局唯一      |
| 6.1             | 按知识层次确定类型；可对齐；避免近义词重复类             | 父类、同义词、命名空间                         | 类型详情、继承           | GENERIC | 无标准核心类对齐/导入治理                       |
| 6.2.2           | 标准实体及其元数据                                       | 通用ENTITY，无专用字段                         | 通用类型/属性            | GENERIC | 无固定IRI、属性和生命周期                       |
| 6.2.3.1         | 标准化对象                                               | 通用实体+属性                                  | 通用建模                 | GENERIC | 无专用类/关系                                   |
| 6.2.3.2         | 相关方：机构、个人、角色                                 | 通用实体/关系；账号不是相关方模型              | 通用建模                 | GENERIC | 组织/个人角色集未标准化                         |
| 6.2.3.3         | 领域类别、ICS/CCS                                        | `BusinessDomain`只组织资产，不等于国标领域类别 | 业务域                   | GENERIC | 需要标准领域类别资产                            |
| 6.2.4.1         | 规范性/资料性要素、状态、作用范围                        | 通用实体；模板核对仅名称/种类                  | 类型/模板                | GENERIC | 无标准要素集和固定属性                          |
| 6.2.4.2         | 章、条、段、列项、标题条、无标题条                       | 类型父类存在；条款资料是扁平记录               | 类型继承/条款            | GENERIC | 标准层次不等于类型继承                          |
| 6.2.5.1         | 术语名称、定义                                           | 通用实体属性                                   | 通用建模                 | GENERIC | 无术语核心模型                                  |
| 6.2.5.2         | 信息单元、条款、附加信息及唯一标识                       | 条款资料不等同信息单元模型                     | 标准条款                 | MISSING | 信息单元/附加信息/全局唯一标识未闭环            |
| 6.2.5.3         | 信息单元表述形式：条文/图/表/公式/附录/引用/提示         | 无专用结构                                     | 无专用页                 | MISSING | 内容与形式未拆成两类实体                        |
| 6.2.5.4–6.2.5.8 | 对象、特性、约束逻辑、行动、外部约束                     | 通用属性/关系/规则可部分表达                   | 类型/关系/规则/导入      | GENERIC | 核心语义是用户自定义                            |
| 6.2.6           | 制定程序及阶段、起止日期                                 | 通用实体/关系可表达；无标准生命周期            | 通用建模                 | GENERIC | 应用本体发布流程不能替代标准程序                |
| 6.3             | 可选版本类、文件编号类、关联属性                         | 资源修订、OWL.versionInfo、本体快照            | 历史、交换               | GENERIC | 无标准版本/文件编号类；标准关系未定义           |
| 7.1             | 属性准确稳定；父类共有核心属性                           | 父类、`rdfs:subClassOf`、冻结继承属性          | 类型继承/详情            | DIRECT  | 标准父类语义仍为空                              |
| 7.2             | 数据属性自身描述、唯一/一致、无传递/对称/互逆            | 类型、枚举、范围、可空性                       | 类型详情、枚举           | DIRECT  | 任意属性唯一规则仍不完整                        |
| 7.3.1           | 对象属性用定义域/值域明确方向                            | 端点、基数、逆关系、`rdfs:domain/range`        | 关系类型/详情            | DIRECT  | 无标准核心关系集                                |
| 7.3.2           | 表1的34个核心对象属性                                    | 任意对象属性可创建                             | 关系类型                 | MISSING | adopts/replaces/cites/hasPart/hasClause等未提供 |
| 8.1             | 公理定义逻辑约束                                         | OWL规则、SHACL规则、OWL2RL一致性               | 规则库/设计器            | DIRECT  | 仅受限可执行子集                                |
| 8.2 a)          | 互斥类、全局唯一标识                                     | `disjointWith`可表达；资源名/IRI唯一           | 规则/创建                | GENERIC | 信息单元等核心类型未落唯一规则                  |
| 8.2 b)          | 唯一属性、日期、枚举、范围                               | 枚举/数值范围有；hasKey/日期先后/唯一元组缺失  | 类型/规则/抽取规则       | GENERIC | 原子规则不能拼成标准8.2规则集                   |
| 8.2 c)          | 功能性、替代、层级、引用区分                             | functional等有；替代/标题条/引用语义缺失       | 关系/规则                | GENERIC | Functional不是闭世界唯一性                      |
| 9.1             | 允许行业扩展                                             | 自定义命名空间/类型/关系/模板                  | 命名空间/类型/关系       | DIRECT  | 核心包版本未批准                                |
| 9.2             | 新命名空间、名称不冲突、约束可加强、模块化、不改核心定义 | 新命名空间/模板可建；protected主要保护删除     | 命名空间/模板            | GENERIC | 核心类型/关系保护边界不足                       |
| A.1             | 类型IRI/Name/Label/Definition/Properties/父/子/等价类    | 资源基础字段、属性、父类、等价类规则           | 类型详情/关系/规则       | DIRECT  | 等价类普通表单、子类视图不足                    |
| A.2             | 属性IRI/Name/Label/Definition/Domain/Range/类型          | 数据属性、端点、属性类型                       | 类型/关系                | DIRECT  | 标准核心属性约束仍缺                            |
| A.3             | 布尔/日期/数值/文本/URI                                  | string/integer/decimal/boolean/date/anyURI     | 数据属性                 | DIRECT  | A.3要求`YYYYMMDD`，当前实例日期验证使用ISO日期  |

## 9. 菜单清晰度诊断

### 9.1 评分

| 维度       | 分数 | 理由                                                         |
| ---------- | ---: | ------------------------------------------------------------ |
| 命名准确性 |  3/5 | 有清楚资产名，但“知识追溯”“版本与交换”“AI助手”混合动作与工具 |
| 分类单一性 |  2/5 | 同组混合对象/动作/输出/配置/模板                             |
| 分组密度   |  3/5 | “本体与资源”8叶子偏高；其他组多数4个                         |
| 任务连续性 |  2/5 | 运行摘要不直达结果集；详情高亮但面包屑丢对象                 |
| 语义唯一性 |  2/5 | 知识库、知识追溯、图谱与追溯、校验报告语义重叠               |
| 入口层级   |  4/5 | 多数高频任务1–2层可达                                        |
| 页面身份   |  3/5 | 设计器/映射/预览是工具或工作台，菜单身份未充分表达           |
| 导航一致性 |  2/5 | 详情、面包屑、返回query、页面标题不统一                      |
| 权限一致性 |  3/5 | Admin隐藏一致；A/E写操作大体一致，但角色说明有冲突           |
| 可发现性   |  3/5 | 快捷搜索和空态可用，但不搜详情/报告/账户                     |

**总分：27/50。**

### 9.2 当前最影响清晰度的三个问题

1. 对象、动作、输出和配置混在同一分类轴。
2. 列表、详情、校验、版本、结果集、图谱之间缺少连续下一步。
3. 隐藏能力（报告、检索、隔离、交换）没有统一发现入口。

### 9.3 不同修复层次

| 只需改标签                                   | 需要改菜单分组                                | 需要改路由/页面边界                         | 需要补国标能力                                   |
| -------------------------------------------- | --------------------------------------------- | ------------------------------------------- | ------------------------------------------------ |
| “本体与资源”“图谱与追溯”“版本与交换”“AI助手” | 语义资产与装配拆分、枚举/模板归位、校验与质量 | 报告中心、运行直达图谱、详情面包屑、URL状态 | 标准核心Profile、核心对象属性、8.2规则、完整交换 |

## 10. 目标方案比较

### 10.1 方案A：任务链优先（推荐）

顶层：

1. 工作台
2. 标准语义资产
3. 本体装配与校验
4. 数据接入与抽取
5. 图谱与证据
6. 治理与版本
7. 知识库
8. 系统管理

逻辑：

- “资产对象”与“工作流阶段”分开；
- 资产创建在标准语义资产；
- 装配、校验和发布在本体装配与校验；
- 数据接入、映射、任务和运行集中在数据接入与抽取；
- 图谱浏览、实例、追溯、报告集中在图谱与证据；
- 知识库独立，因为它处理非结构化文档和检索，不是图谱结果集。

优点：适合一线建模、数据接入、抽取、追溯用户。
代价：菜单需要重新分组，但首期不需要改路径。

### 10.2 方案B：资产生命周期优先

顶层：工作台 / 语义模型资产 / 本体装配资产 / 数据接入资产 / 映射与抽取资产 / 结果资产 / 治理与交换 / 知识库 / 系统管理。

逻辑：按资产类别组织，尤其适合资产治理人员。

优点：对象直觉强，资产归属稳定。
代价：跨资产生命周期操作需要更长路径；一线业务流程被拆到多个组。

### 10.3 方案C：最小改动

保留现有7/8个一级菜单，只做：

- 重命名；
- 调整图标和顺序；
- 在现有组内增加二级分组；
- 修复菜单/路由漂移；
- 清理同名能力。

优点：风险最低，不破坏书签。
代价：不能根本解决分类轴混合、报告发现、详情导航和国标能力缺口。

### 10.4 推荐

采用 **方案A**，并分两阶段：

1. 第一阶段：只做菜单重排和数据驱动，不改 route name、path、页面文件；
2. 第二阶段：在保留旧链接的前提下调整少数页面边界和报告中心。

## 11. 目标信息架构（方案A）

### 11.1 目标菜单

```text
工作台

标准语义资产
├─ 命名空间
├─ 实体类型库
├─ 关系类型库
├─ 业务域
└─ 资产配置与模板
   ├─ 枚举词典
   └─ 装配模板

本体装配与校验
├─ 本体库
├─ 本体设计器
└─ 校验与质量

数据接入与抽取
├─ 数据源
├─ 数据目录
├─ 映射工作台
├─ 抽取任务
└─ 抽取运行

图谱与证据
├─ 图谱浏览
├─ 实体实例
└─ 证据追溯

治理与版本
├─ 标准条款
├─ 规则库
└─ 版本与交换

知识库

系统管理（ADMIN）
├─ 用户管理
├─ 角色与能力
├─ 操作与资产审计
└─ AI 模型配置
```

### 11.2 菜单修正说明

| 旧菜单     | 新菜单                          | 变化                   | 路由是否变更  | 页面文件是否变更 |
| ---------- | ------------------------------- | ---------------------- | ------------- | ---------------- |
| 工作台     | 工作台                          | 保持                   | 否            | 否               |
| 知识库     | 知识库                          | 保持为一级目的地       | 否            | 否               |
| 本体与资源 | 标准语义资产 + 本体装配与校验   | 按资产/装配拆分        | 否            | 第一阶段否       |
| 本体库     | 本体库                          | 保留为装配列表         | 否            | 否               |
| 本体设计器 | 本体设计器                      | 保留为工作台           | 否            | 否               |
| 实体类型库 | 实体类型库                      | 保留                   | 否            | 否               |
| 关系类型库 | 关系类型库                      | 保留                   | 否            | 否               |
| 业务域     | 业务域                          | 保留                   | 否            | 否               |
| 命名空间   | 命名空间                        | 保留为语义身份配置     | 否            | 否               |
| 枚举词典   | 资产配置与模板 → 枚举词典       | 归位                   | 否            | 第一阶段否       |
| 装配模板   | 资产配置与模板 → 装配模板       | 归位                   | 否            | 第一阶段否       |
| 数据接入   | 数据接入与抽取                  | 合并数据/映射/抽取语义 | 否            | 否               |
| 数据源     | 数据接入与抽取 → 数据源         | 保留                   | 否            | 否               |
| 数据目录   | 数据接入与抽取 → 数据目录       | 保留                   | 否            | 否               |
| 样例预览   | 数据目录的上下文工具            | 降为工具               | 否            | 否               |
| 映射与抽取 | 数据接入与抽取                  | 合并                   | 否            | 否               |
| 映射向导   | 映射工作台                      | 标签修正               | 第一/二阶段否 | 第二阶段可迁移   |
| AI 助手    | 映射工作台/抽取工具的上下文工具 | 降为工具               | 否            | 第二阶段可迁移   |
| 抽取任务   | 抽取任务                        | 保留                   | 否            | 否               |
| 抽取运行   | 抽取运行                        | 保留                   | 否            | 否               |
| 图谱与追溯 | 图谱与证据                      | 标签修正               | 否            | 否               |
| 图谱浏览   | 图谱浏览                        | 保留                   | 否            | 否               |
| 实体实例   | 实体实例                        | 保留                   | 否            | 否               |
| 知识追溯   | 证据追溯                        | 标签修正               | 否            | 否               |
| 校验报告   | 校验与质量 → 校验报告           | 移出图谱工具           | 第二阶段      | 第二阶段可迁移   |
| 治理与版本 | 治理与版本                      | 保留                   | 否            | 否               |
| 规则库     | 规则库                          | 保留                   | 否            | 否               |
| 标准条款   | 标准条款                        | 保留                   | 否            | 否               |
| 版本与交换 | 版本与交换                      | 保留用户标签           | 第二阶段      | 第二阶段可迁移   |
| 系统管理   | 系统管理                        | 保留                   | 否            | 否               |

### 11.3 详情页、面包屑与搜索统一规则

1. **详情页不进入菜单**，继续由列表/图谱/知识库进入。
2. 详情面包屑必须包含对象层：

```text
标准语义资产 / 实体类型库 / Employee
标准语义资产 / 关系类型库 / WorksFor
图谱与证据 / 实体实例 / Employee
知识库 / Human Resources / 文档
```

3. 详情页返回列表时保留 `q/status/domain/page/sort/graph/center/kbReturn` 等上下文。
4. 快捷搜索索引：

   - 菜单叶子和页面标题；
   - 安全的详情入口名称；
   - 账户页；
   - “校验报告”“证据追溯”等页面别名；
   - 不按真实资产名称泄露不可见资源。

5. 页面标题统一由路由 `meta.title` + i18n 生成；浏览器标题随语言和路由变化。

### 11.4 校验与质量中心的边界

“校验与质量”不是把设计器里的校验面板复制一份，而是提供：

- 历史报告列表或按报告 ID 载入；
- 本体资产校验、图谱实例校验；
- 四态筛选：PASS / VIOLATION / NA / NOT_RUN；
- focus node → 资源详情/图谱；
- rule id → 规则；
- 报告导出；
- 明确显示检查覆盖范围与未执行项。

### 11.5 运行结果的下一步

抽取运行摘要应提供：

- “查看本次结果集图谱” → `graph-browse?graph=<id>`；
- “查看隔离明细” → 隔离列表；
- “查看校验报告”；
- “导出运行报告”；
- 当前集切换仍保留为受权限控制的结果集动作。

## 12. 新目录结构

> 以下是**目标目录结构**，不是本轮已移动的文件。第一阶段优先通过菜单配置、导航层和页面内边界达成目标；文件搬迁只在第二阶段或更后阶段，且必须保留旧路由和深链。

### 12.1 设计原则

1. 页面按**业务域**组织，不按菜单视觉顺序组织。
2. 页面私有组件、私有组合式函数和测试与页面同域。
3. 跨业务域复用才进入 `components/`、`composables/` 或明确共享模块。
4. API 按业务域拆文件，页面不直接依赖内部 HTTP 实现。
5. 菜单和路由身份分离：菜单可重排，route name 和 path 尽量先保持稳定。
6. 新标准核心Profile放在语义层，不通过伪造页面或目录“实现合规”。

### 12.2 前端目标目录树

```text
web/src/
├── api/
│   ├── client.ts
│   ├── tokens.ts
│   ├── schema.d.ts
│   ├── auth.ts
│   ├── dashboard.ts
│   ├── ontology.ts
│   ├── namespaces.ts
│   ├── entity-types.ts
│   ├── relations.ts
│   ├── domains.ts
│   ├── enum-dictionaries.ts
│   ├── templates.ts
│   ├── governance.ts
│   ├── clauses.ts
│   ├── validation.ts
│   ├── ontology-history.ts
│   ├── ontology-restore.ts
│   ├── datasources.ts
│   ├── mappings.ts
│   ├── extraction.ts
│   ├── graph.ts
│   ├── knowledge.ts
│   ├── ai.ts
│   ├── ai-models.ts
│   └── asset-audit.ts
├── components/
│   ├── AppIcon.vue
│   ├── PageHeader.vue
│   ├── StarMark.vue
│   ├── icons.ts
│   └── graph/
│       └── viewport.ts          # 仅当跨 ontology/graph 复用时上移
├── composables/
│   ├── useApiError.ts
│   ├── useAsyncData.ts
│   ├── useDraftGuard.ts
│   └── graph/
│       └── useGraphViewport.ts  # 与页面无关的图形交互原语
├── i18n/
│   └── index.ts
├── locales/
│   ├── zh-CN.json
│   └── en-US.json
├── layout/
│   ├── AdminLayout.vue
│   ├── AuthLayout.vue
│   ├── components/
│   │   ├── AppHeader.vue
│   │   ├── AppSider.vue
│   │   ├── QuickSearch.vue
│   │   └── UserDropdown.vue
│   └── navigation/
│       ├── menuConfig.ts        # 菜单单一真值
│       ├── routeIdentity.ts     # route name、详情 fallback、页面标题
│       └── searchIndex.ts       # 可发现性索引
├── router/
│   ├── index.ts                 # 路由创建与守卫
│   ├── auth.ts                  # 公开认证路由，可按需拆分
│   ├── main.ts                  # 主业务路由，可按需拆分
│   └── guards.ts                # 登录/管理员守卫
├── stores/
│   ├── index.ts
│   ├── auth.ts
│   ├── locale.ts
│   └── ui.ts
├── styles/
│   ├── tokens.css
│   └── ...
├── views/
│   ├── dashboard/
│   │   └── DashboardPage.vue
│   ├── knowledge/
│   │   ├── KnowledgeBaseListPage.vue
│   │   ├── KnowledgeBaseDetailPage.vue
│   │   ├── KnowledgeSearchPage.vue
│   │   ├── components/
│   │   │   ├── BaseEditor.vue
│   │   │   ├── DocumentDrawer.vue
│   │   │   ├── EvidenceDrawer.vue
│   │   │   ├── GraphLinkForm.vue
│   │   │   └── SearchHit.vue
│   │   ├── composables/
│   │   │   └── useKnowledge.ts
│   │   ├── knowledge.css
│   │   └── __tests__/
│   ├── semantic-assets/
│   │   ├── namespaces/
│   │   │   ├── NamespacesPage.vue
│   │   │   └── components/NamespaceCreateModal.vue
│   │   ├── entity-types/
│   │   │   ├── EntityTypesPage.vue
│   │   │   ├── EntityTypeDetailPage.vue
│   │   │   └── __tests__/
│   │   ├── relation-types/
│   │   │   ├── RelationTypesPage.vue
│   │   │   ├── RelationTypeDetailPage.vue
│   │   │   └── components/RelationSemanticFields.vue
│   │   ├── business-domains/
│   │   │   └── BusinessDomainsPage.vue
│   │   ├── enum-dictionaries/
│   │   │   └── EnumDictionariesPage.vue
│   │   ├── assembly-templates/
│   │   │   └── AssemblyTemplatesPage.vue
│   │   ├── components/          # 仅本域复用
│   │   ├── composables/
│   │   └── __tests__/
│   ├── ontology/
│   │   ├── OntologiesPage.vue
│   │   ├── DesignerPage.vue
│   │   ├── components/
│   │   │   ├── AiSuggestions.vue
│   │   │   ├── AiModeling.vue
│   │   │   └── designerGeometry.ts
│   │   ├── composables/
│   │   │   └── useDesignerHistory.ts
│   │   └── __tests__/
│   ├── validation/
│   │   ├── ValidationReportsPage.vue
│   │   ├── components/
│   │   │   ├── ValidationSummary.vue
│   │   │   └── ValidationResultsTable.vue
│   │   └── __tests__/
│   ├── data-integration/
│   │   ├── sources/DataSourcesPage.vue
│   │   ├── catalog/DataCatalogPage.vue
│   │   └── preview/SamplePreviewPage.vue
│   ├── extraction/
│   │   ├── mapping/
│   │   │   ├── MappingWorkbenchPage.vue
│   │   │   └── components/
│   │   │       ├── ExtractionSuggestions.vue
│   │   │       ├── FrozenMapping.vue
│   │   │       └── FusionPolicyEditor.vue
│   │   ├── tasks/ExtractionTasksPage.vue
│   │   ├── runs/ExtractionRunsPage.vue
│   │   ├── ai-assist/AiAssistPage.vue
│   │   └── __tests__/
│   ├── graph/
│   │   ├── browse/
│   │   │   └── GraphBrowsePage.vue
│   │   ├── entities/
│   │   │   ├── GraphEntitiesPage.vue
│   │   │   └── GraphEntityDetailPage.vue
│   │   ├── evidence/
│   │   │   └── GraphEvidencePage.vue
│   │   ├── components/
│   │   │   ├── EvidenceInspector.vue
│   │   │   ├── EvidenceTable.vue
│   │   │   ├── GraphCanvas.vue
│   │   │   ├── GraphFactTable.vue
│   │   │   └── KnowledgeGraphReferences.vue
│   │   ├── composables/
│   │   │   └── useFrozenRelationLabels.ts
│   │   └── __tests__/
│   ├── governance/
│   │   ├── clauses/StandardClausesPage.vue
│   │   ├── rules/GovernanceRulesPage.vue
│   │   ├── exchange/OntologyExchangePage.vue
│   │   ├── components/
│   │   │   ├── OntologyHistory.vue
│   │   │   └── OntologyRestore.vue
│   │   └── __tests__/
│   ├── account/
│   │   ├── ProfilePage.vue
│   │   └── SecurityPage.vue
│   ├── auth/
│   │   ├── LoginPage.vue
│   │   ├── RegisterPage.vue
│   │   ├── ForgotPasswordPage.vue
│   │   ├── ResetPasswordPage.vue
│   │   └── AuthHeading.vue
│   ├── system/
│   │   ├── UsersPage.vue
│   │   ├── RolesPage.vue
│   │   ├── AuditLogsPage.vue
│   │   ├── AiModelsPage.vue
│   │   └── components/AssetAuditLogs.vue
│   └── errors/
│       ├── ForbiddenPage.vue
│       └── NotFoundPage.vue
└── main.ts
```

### 12.3 新目录的职责约束

| 目录                         | 职责                                 | 禁止                               |
| ---------------------------- | ------------------------------------ | ---------------------------------- |
| `web/src/api/`               | 按业务域请求、类型、响应解包适配     | 导入页面、组件、路由、Pinia、i18n  |
| `web/src/components/`        | 至少两个业务域复用的纯展示或通用交互 | 读取页面路由、直接发起领域请求     |
| `web/src/components/graph/`  | 跨域共享图形工具                     | 存放只被一个页面使用的页面私有组件 |
| `web/src/composables/`       | 跨业务域复用组合式逻辑               | 页面专属数据编排                   |
| `web/src/layout/navigation/` | 菜单、路由身份、可发现性索引         | 领域请求和页面业务判断             |
| `web/src/views/<area>/`      | 页面及私有组件、组合式函数、测试     | 跨域私有导入                       |
| `web/src/router/`            | 稳定路由身份、守卫、重定向           | 页面专属领域请求                   |
| `web/src/stores/`            | 登录、语言、主题、布局偏好           | 单页筛选、表单草稿、一次性请求     |

### 12.4 目标路由身份和文件边界

第一阶段保持现有 route name 与 path；第二阶段如需迁移，按下表处理：

| 当前 route name      | 当前 path               | 目标页面身份         | 第二阶段建议                                   | 兼容要求                   |
| -------------------- | ----------------------- | -------------------- | ---------------------------------------------- | -------------------------- |
| `ontologies`         | `/ontology/ontologies`  | Ontology list        | 保持                                           | 旧深链不变                 |
| `designer`           | `/ontology/designer`    | Ontology workbench   | 可选 `/ontology/designer`，增加本体 query 同步 | 旧 `?ontology=` 可用       |
| `mapping-wizard`     | `/extraction`           | Mapping workbench    | 可选 `/extraction/mappings`                    | `/extraction` 重定向或别名 |
| `sample-preview`     | `/datasources/preview`  | Data catalog tool    | 不推荐改为一级入口                             | 旧入口仍可从目录进入       |
| `ai-assist`          | `/extraction/ai-assist` | Extraction tool      | 保留工具路径                                   | 不进入固定一级菜单         |
| `graph-reports`      | `/graph/reports`        | Validation & quality | 可选 `/validation/reports`                     | 旧路径重定向               |
| `ontology-export`    | `/governance/export`    | Version & exchange   | 可选 `/governance/exchange`                    | 旧路径重定向               |
| `governance-clauses` | `/governance/clauses`   | Standard clauses     | 保持                                           | 旧深链不变                 |

### 12.5 菜单配置目标文件

建议把菜单从 `useNavigation.ts` 中的内联树抽成纯数据：

```text
web/src/layout/navigation/menuConfig.ts
```

结构示意：

```ts
export type MenuLeaf = {
  key: string // 必须等于 route name
  labelKey: string
  kind: 'destination' | 'workbench' | 'tool' | 'admin'
  visibleTo: 'AUTHENTICATED' | 'ADMIN'
}

export type MenuSection = {
  id: string
  labelKey: string
  icon: IconName
  children: MenuLeaf[]
}

export const menuSections: MenuSection[] = [
  // 标准语义资产、本体装配与校验、数据接入与抽取、
  // 图谱与证据、治理与版本、系统管理
]
```

约束：

- 叶子 `key` 必须能解析为真实 route name；
- 分组 key 不参与跳转；
- 菜单标签只来自 i18n；
- 详情页不进入菜单；
- 工具页可以出现在菜单，但必须标记为 `tool`，不要伪装成资产；
- 旧链接不做菜单项重命名式破坏，使用route alias/redirect。

### 12.6 后端目标支撑结构

标准核心Profile不应成为菜单层伪造的数据，也不应把国标全部塞进通用 `utils.py`。如果进入第二阶段能力补齐，建议新增最小语义支撑：

```text
server/app/
├── semantics/
│   └── profiles/
│       ├── __init__.py
│       ├── base.py
│       └── gbt48000_3_2026/
│           ├── manifest.json
│           ├── core-classes.ttl
│           ├── core-properties.ttl
│           ├── core-shapes.ttl
│           └── README.md
├── schemas/
│   └── standard_profile.py
└── domain/
    └── standard_profile_service.py
```

约束：

- RDF/OWL/SHACL 依赖只出现在 `semantics/`；
- `domain` 通过稳定接口编排，不直接散落 rdflib 细节；
- Profile 必须有版本、IRI、发布状态、适用范围和校验结果；
- 未批准的 Profile 只能显示为 NOT_RUN 或不可用，不能显示“符合”；
- 不在菜单里为每个标准类创建一级入口。

### 12.7 文档目录目标

```text
docs/
├── knowledge-information-architecture-2026-11-21.zh-CN.md  # 本文
├── adr/
│   ├── 0001-backend-stack.md
│   ├── 0002-account-auth.md
│   ├── 0003-business-asset-audit.md
│   ├── 0004-information-architecture-gbt48000.md            # 方案批准后新增
│   └── ...
├── audit-2026-11-06/                                         # 历史审计，不作为当前证明
├── knowledge-mvp-2026-11-08/                                 # 历史验证
├── ui-redesign-2026-11-07/                                   # 历史设计证据
└── ...
```

## 13. 分阶段迁移计划

### 阶段0：固化基线与测试（只读/测试）

**目标**：在改菜单前，证明当前路由、菜单、详情回退和搜索行为。

交付：

- 路由 name 唯一性检查；
- 菜单 key → 真实 route 解析检查；
- 详情 fallback 配置检查；
- 角色可见性快照；
- QuickSearch 当前索引快照；
- 旧路径/重定向清单。

验收：

- 所有现有路由可解析；
- 所有菜单叶子有页面；
- 详情回退不制造假高亮；
- 搜索只显示可见角色可以进入的页面。

### 阶段1：菜单重排（不改 path）

**目标**：采用方案A的菜单分组和标签，不改变现有 route name、path、页面文件。

交付：

- `menuConfig.ts`；
- 新一级分组与叶子排序；
- 工具页标记；
- 旧菜单组被移除但所有路由仍可访问；
- 快捷搜索索引同步菜单。

验收：

- `/ontology/entity-types`、`/ontology/designer`、`/graph/entities` 等旧深链全部可用；
- 菜单高亮在刷新、直接进入、前进后退后正确；
- 1440px 与 375px 菜单无溢出；
- ADMIN 系统管理可见，VIEWER不可见；
- 不出现“只有一个子项却包装成一级分组”的新问题。

### 阶段2：详情与上下文（路由边界不变）

**目标**：补齐详情面包屑、返回路径、筛选保留和浏览器标题。

交付：

- `routeIdentity.ts` 统一详情 fallback；
- 实体、关系、知识库、图谱实体详情的对象层面包屑；
- `q/status/page/sort/graph/center/kbReturn` 上下文策略；
- `meta.title` 全路由；
- `document.title` 响应语言变化。

验收：

- 列表→详情→返回保留筛选；
- 直接打开详情深链→刷新→面包屑正确；
- 浏览器前进/后退不覆盖对象身份；
- 375px 面包屑不导致页面溢出。

### 阶段3：校验与质量中心

**目标**：把“校验报告”从图谱工具变成可发现的质量能力。

交付：

- 历史报告列表或报告 ID 载入；
- 报告导出；
- 四态筛选、focus node、rule id、binding 展示；
- VIEWER可查看既有报告；
- 设计器校验面板可跳转报告中心。

验收：

- PASS/VIOLATION/NA/NOT_RUN 均可见且不混淆；
- 没有执行的自然显示 NOT_RUN；
- 报告 ID、目标版本、binding 不被丢失；
- 旧 `/graph/reports` 路径仍可用。

### 阶段4：抽取运行到图谱/隔离

**目标**：闭合抽取运行结果与证据治理。

交付：

- 运行摘要 → 对应 graph revision；
- 隔离明细列表；
- 隔离原因/字段/来源行；
- 运行摘要 → 校验报告；
- 失败/取消运行保持“结果受保护”。

验收：

- 一轮成功运行可从摘要一步到对应图谱；
- 失败运行不错误切换当前集；
- 隔离明细不是数量警告；
- 旧运行记录仍可查看。

### 阶段5：标准核心Profile与规则闭环

**目标**：在模型、序列化、校验层补齐国标核心能力，不机械新增菜单。

交付：

- 6.2核心实体类型包；
- 表1核心对象属性包；
- 8.2核心规则可执行子集；
- 附录A元数据；
- 标准核心Profile的版本和符合性报告；
- OWL/SHACL规则完整导入导出/恢复。

验收：

- 核心实体、属性、关系可用固定IRI；
- 关键规则有PASS/VIOLATION/NOT_RUN；
- 独立数据库导出→恢复→再导出同构；
- 不能把通用模型或空校验报告宣传为国标符合。

### 阶段6：可选路径/文件迁移

**目标**：在业务验收后归一页面身份，非前置条件。

可选项：

- `ontology-export` → `versions-exchange`；
- `graph-reports` → `validation-reports`；
- `views/governance/` 中枚举/模板按目标目录事务性迁移；
- `Designer` 的私有 graphViewport 依赖上移为共享组合式函数。

兼容要求：

- 旧 path 必须有 redirect/alias；
- 旧 route name 如被外部书签使用，需保留至少一个兼容窗口；
- 页面文件迁移必须和测试、imports、API模块、i18n同步；
- 不为目录整齐单独搬迁。

## 14. 问题清单与优先级

| ID    | 类型          | 优先级 | 当前证据                                                   | 用户影响             | 最小修正                        | 验收方式                                    |
| ----- | ------------- | ------ | ---------------------------------------------------------- | -------------------- | ------------------------------- | ------------------------------------------- |
| C-01  | 国标模型缺口  | P0     | 标准Profile不支持；M05不运行                               | 不能宣称国标符合     | 引入版本化标准核心Profile       | 条款映射、M05真实执行、报告明确边界         |
| C-02  | 国标模型缺口  | P1     | 6.2核心实体无固定模型                                      | 用户需猜测核心类型   | 提供核心实体类型包              | 8类核心实体有固定IRI、属性和关系            |
| C-03  | 国标模型缺口  | P1     | 表1核心关系无标准词汇                                      | 标准本体交换不稳定   | 建立核心对象属性包              | 34个核心属性的domain/range/方向和约束可导出 |
| C-04  | 国标模型缺口  | P1     | HAS_KEY/DATE_ORDER/UNIQUE_TUPLE/CONDITIONAL_REQUIRED不支持 | 8.2规则缺失          | 扩展可执行规则子集并显式NOT_RUN | 每类规则有正反例和四态结果                  |
| C-05  | 国标模型缺口  | P1     | 规则快照阻断完整恢复                                       | 带规则本体不能交换   | 支持规则恢复或等价安全导入策略  | export→restore→re-export同构                |
| C-06  | 国标模型缺口  | P1     | 日期模型语义与A.3不一致                                    | 日期解释错误风险     | 增加标准日期词法/约束           | 非法词法拒绝，标准日期可往返                |
| C-07  | 国标模型缺口  | P1     | protected主要保护命名空间删除                              | 核心身份稳定性不足   | 扩展到核心资源编辑/改名         | 核心资源不可被普通改写，历史快照保持        |
| F-01  | 前端能力缺口  | P1     | 报告页无历史报告/ID载入；VIEWER无查看入口                  | 历史合规证据不可发现 | 报告中心                        | VIEWER可载入/筛选/导出报告                  |
| F-02  | 前端能力缺口  | P1     | runQuarantine无调用点                                      | 无法定位隔离字段     | 隔离明细                        | 列表显示理由、字段、来源行、运行            |
| F-03  | 前端能力缺口  | P1     | 运行摘要无结果集图谱入口                                   | 用户需绕行           | 摘要加直达链接                  | 运行→结果集一步且ID正确                     |
| IA-01 | 菜单语义冲突  | P1     | 本体与资源8叶子混合分类轴                                  | 用户不知入口         | 方案A重排                       | 菜单同类同层、旧路由不坏                    |
| IA-02 | 菜单语义冲突  | P1     | 知识库/知识追溯/图谱与追溯/证据重叠                        | 用户混淆文档与图谱   | 统一证据层级                    | 菜单/标题/页面身份可区分                    |
| IA-03 | 可发现性问题  | P1     | QuickSearch只搜菜单标签                                    | 已有能力显得不存在   | 搜索索引扩展                    | 安全命中页面标题、报告、账户和详情返回      |
| N-01  | 路由/文件漂移 | P2     | `ontology-export/export`实际含历史/导入/导出               | 深链语义滞后         | 第二阶段加exchange身份          | 新链接可用，旧链接重定向                    |
| N-02  | 路由/文件漂移 | P2     | 枚举/模板菜单属resources、页面属governance                 | 菜单/代码理解分裂    | 菜单先归位，页面后迁移          | 菜单、路由、目录、API语义一致               |
| A-01  | 路由/文件漂移 | P2     | Designer导入graph私有viewport                              | 跨域变更耦合         | 上移共享graph原语               | 跨域边界检查通过                            |
| A-02  | 可发现性问题  | P2     | useAsyncData把资源不存在翻译为图谱专用文案                 | 非图谱页误导         | 域级错误映射                    | 工作台/AI/模板页不再出现图谱专属下一步      |
| P-01  | 权限/状态风险 | P2     | 角色说明“测试能力是”但测试控件A/E                          | 能力认知错误         | 角色能力按实际门禁生成          | 角色页与实际按钮一致                        |
| N-03  | 可发现性问题  | P2     | meta.title有限且不生成浏览器标题                           | 多标签/刷新识别差    | 统一页面标题                    | 1440/375、切语言、前进后退标题稳定          |

## 15. 验证计划

### V0｜静态检查

- 路由 name 唯一；
- 菜单 key 全部解析为真实 route name；
- 分组 key 不执行导航；
- 详情 fallback 正确；
- 权限元数据一致；
- 没有重复菜单标签；
- 没有孤立页面；
- 旧 path redirect/alias 存在；
- 页面文件不存在跨域私有导入（至少禁止 `Designer → graphViewport` 私有路径）。

### V1｜定向页面测试

- 菜单渲染、展开/收起、高亮；
- 面包屑和返回路径；
- 快捷搜索、清空、无结果、快捷键盘；
- ADMIN/EDITOR/VIEWER角色可见性；
- 空态、错误态、权限不足态；
- 四态结果与`NOT_RUN`显示；
- 旧 query 保留（筛选、页码、图谱、知识库返回）。

### V2｜浏览器走查

使用仓库隔离的 Playwright 配置，不复用开发数据库或真实源库：

- 1440×900 和 1920×1080；
- 375px 窄屏；
- 直接打开详情深链；
- 刷新后高亮；
- 前进/后退；
- 键盘焦点；
- 旧链接 redirect；
- 登录失败、权限不足、空态和报告无记录；
- 关键任务链 A–E 的真实可观察结果。

### V3｜按实际影响决定

- 主流程端到端；
- RDF/OWL/SHACL导入导出往返；
- 标准核心Profile校验；
- 四态与发布门禁；
- 路由兼容；
- 真实 PostgreSQL/MySQL、远端数据源、真实 LLM/Embedding；
- 完整CI、构建和发布链路。

### 建议执行顺序

1. 阶段0静态基线；
2. 阶段1菜单重排，不改路径；
3. 阶段2详情/面包屑/搜索/页面标题；
4. 阶段3校验与质量中心；
5. 阶段4运行→图谱/隔离；
6. 阶段5标准核心Profile与规则闭环；
7. 阶段6在保留旧链接前提下做路径和文件迁移。

## 16. 本轮不做什么

- 不修改任何应用源码、路由、菜单、目录；
- 不移动页面；
- 不新增、删除或改动应用路由；
- 不执行迁移、构建、发布或完整 E2E；
- 不将静态路由存在写成浏览器已验证；
- 不将通用实体、通用属性、页面存在、目录整齐写成“国标符合”；
- 不用方案A替代国标核心模型；
- 不把国标条款和前端菜单一一对应；
- 不在阶段0/1改变用户已有深链。

## 17. 需要确认的边界

1. 是否确认采用 **方案A：任务链优先**？
2. 是否接受阶段1只重排菜单、不改 route name、path、页面文件？
3. 是否将“校验与质量”作为独立目的地，先复用 `/graph/reports`，后续再评估路径迁移？
4. 是否将标准核心Profile、核心对象属性、8.2规则纳入下一阶段，而不是只做菜单层调整？
5. 是否允许第二阶段在保留旧链接的前提下，把 `ontology-export` 和 `graph-reports` 迁移到更准确的路由/文件身份？
6. 是否要求下一阶段同时补齐运行→图谱、隔离明细、既有报告、知识库证据到图谱的上下文链？
7. 是否接受 `views/semantic-assets/`、`views/ontology/`、`views/validation/` 等目标目录作为**渐进迁移目标**，而不是立即大规模搬迁？

## 18. 结论

当前应用的产品边界和部分任务链已经成立，但：

- 通用本体模型不能自动升级为国标符合；
- 当前菜单的主要问题不是“页面数量”，而是分类轴、任务连续性、语义唯一性和可发现性；
- 新目录结构应服务于业务域和任务链，而不是为了目录整齐；
- 最稳妥的实施顺序是“先固化基线 → 菜单重排 → 详情/搜索/报告 → 运行/隔离 → 标准核心Profile与规则闭环 → 最后再评估文件和路径迁移”。

在用户确认上述目标IA、迁移边界和国标能力范围前，不进入菜单重排、路由变更或文件搬迁。

## 附录 A：文档制作与交付核对

| 项            | 结果                                                                                                                   |
| ------------- | ---------------------------------------------------------------------------------------------------------------------- |
| 文件          | `docs/knowledge-information-architecture-2026-11-21.zh-CN.md`                                                          |
| 格式          | Markdown                                                                                                               |
| 章节          | 19 个一级章节 + 附录                                                                                                   |
| 内容          | 一页结论、能力树、菜单树、路由矩阵、任务链、国标映射、IA评分、方案比较、目标IA、目标目录、迁移阶段、问题清单、验证计划 |
| 应用源码      | 未修改                                                                                                                 |
| 应用路由/菜单 | 未修改                                                                                                                 |
| 页面文件      | 未移动                                                                                                                 |
| 构建/测试/E2E | 未执行                                                                                                                 |
| 静态检查      | Markdown fences 平衡；`git diff --cached --check` 通过                                                                 |
| Git 状态      | 本文档已暂存；审计前已有的其他工作区改动未被覆盖或清理                                                                 |

### A.1 实施前核对

在进入任何实施前，必须确认：

- [ ] 目标IA方案已确定；
- [ ] 菜单层级和标签已确认；
- [ ] 是否保持 route name/path 已确认；
- [ ] 详情页 fallback 和 breadcrumb 规则已确认；
- [ ] 校验报告、隔离明细、运行直达图谱是否在本轮范围已确认；
- [ ] 国标核心Profile是否在下一阶段已确认；
- [ ] 允许修改的文件边界已确认；
- [ ] 旧链接兼容窗口已确认。

### A.2 实施后最低验收

- [ ] `make lint` 或受影响范围的等量静态检查通过；
- [ ] 定向前端测试通过；
- [ ] 路由 name、菜单 key、详情 fallback、权限元数据检查通过；
- [ ] 1440px、375px 菜单与详情页无横向溢出；
- [ ] 直接打开详情深链、刷新、前进/后退均正确；
- [ ] QuickSearch 只返回当前角色可见目的地；
- [ ] 旧 path redirect/alias 可用；
- [ ] `git status` 中没有 demo、依赖、venv、dist 等非交付物；
- [ ] 交付说明区分已验证、局部验证、未验证。

## 附录 B：建议的首次实施切片

如果确认采用方案A，建议第一次实施**只做以下切片**：

1. 新建 `web/src/layout/navigation/menuConfig.ts`；
2. 将菜单标签改成目标IA的第一层名称；
3. 将枚举词典与装配模板放入“资产配置与模板”二级层；
4. 将样例预览、AI助手标记为工具而不是业务资产；
5. 将校验报告暂时放在“本体装配与校验 → 校验与质量”，但仍使用原 `/graph/reports`；
6. 保持所有 route name 与 path 不变；
7. 保持详情页、报告页、运行页原行为不变；
8. 只增加静态一致性测试和一次1440/375浏览器检查。

这个切片的交付标准是：

- 用户能看懂新菜单；
- 所有旧深链仍然可用；
- 不改页面文件、不改API、不做国标Profile；
- 失败时只回滚菜单配置，不影响业务路由和页面。

完成此切片并验收后，再进入详情面包屑、报告中心、运行→图谱和标准核心Profile阶段。
