# 前端实现与原设计方案一致性核查报告

> 核查日期：2026-09-24 · 范围：`web/` 前端全部源码 + 真实运行实测
> 对照基线：`design/*.html`（7 份设计稿 / 32 屏，2026-09-23）、`docs/frontend-redesign-plan.zh-CN.md`、`docs/implementation-plan.zh-CN.md`（47 项功能与 DoD）、`README.md`

## 0. 核查方法与环境说明

**方法**：源码逐文件审读 → 真实启动前后端（uvicorn + vite）→ Chromium 实测 25 条路由并量化测量 DOM/CSS → 对关键结论做受控对比实验（注入样式前后对照）。

**环境说明（影响结论，先读）**：`server/knowledge.db` 的结构落后于迁移，缺少 `business_domain.edit_revision` 列。未迁移时 `/api/v1/domains` 与 `/api/v1/ontologies` 直接返回 **500**，业务域页与本体设计器页完全不可用。本报告中的页面级结论均在**已执行 `alembic upgrade head` 的数据库副本**上取得，以避免环境噪声污染前端结论。详见 §6.1。

**实测覆盖**：25 条路由全部实测，无横向滚动条（`scrollWidth <= innerWidth` 全部为 true），无运行时报错（除 §6.1 的迁移问题）。

---

## 1. 结论摘要

| 编号 | 问题                                                                         | 严重度 | 位置                                  |
| ---- | ---------------------------------------------------------------------------- | ------ | ------------------------------------- |
| A1   | **左侧导航栏未实现自适应高度**（实测侧栏高 422~852px，视口 900px，从不相等） | P0     | `layout/AdminLayout.vue:34`           |
| D1   | **实体类型无法编辑基本信息**（名称/标签/定义只读，只能改数据属性）           | P0     | `views/ontology/EntityDetail.vue:417` |
| D4   | **关系类型无法发布**（后端有 publish，前端 API 未接）→ 草稿永久锁死          | P0     | `api/relations.ts:17`                 |
| D6   | **业务域无法编辑**（后端有 PUT，前端 API 未接）                              | P1     | `api/domains.ts:13`                   |
| C1   | 12 个业务页面表单**无字段级校验**（无 rules/path/feedback/必填标记）         | P1     | 见 §4 清单                            |
| B2   | 设计系统「紫色 AI 轴」与「AI 辅助入口」**完全未实现**（五大签名元素之一）    | P1     | 全站                                  |
| A6   | 内容区不撑满视口，**每页底部大片空白**（同上根因）                           | P1     | `layout/AdminLayout.vue:40`           |
| B1   | 正文 14px ≠ 设计规定 13px                                                    | P2     | `styles/tokens.css:98`                |
| D12  | 实体详情 6 个页签中 **3 个是空占位**（关联关系/规则/引用与版本）             | P1     | `EntityDetail.vue:483-491`            |
| —    | 其余见 §2~§5                                                                 | —      | —                                     |

---

## 1.1 修复进度（2026-09-24 更新）

本报告的结论已按批次落地，对应提交：

| 提交      | 内容                                             | 覆盖本报告条目                   |
| --------- | ------------------------------------------------ | -------------------------------- |
| `45bbea0` | 修复侧栏与内容区高度塌陷                         | A1、A6、A5（设计器高度算法解耦） |
| `da372b8` | 补齐实体类型、关系类型与业务域的写操作入口       | D1、D4、D6、D7                   |
| `6b03531` | 业务表单改为字段级校验                           | C1、C2、C3、C4                   |
| `d2fdcbc` | 错误响应统一外壳，元数据库异常单独成码           | §6.1                             |
| `a2842e6` | 修复全屏页顶部被裁、统计卡光晕外溢与表格列宽塌陷 | A5 补充、B7、§6.1 关联           |
| `8e818e6` | 补本体库列表与新建本体入口                       | §5.7（本轮新发现）               |
| `aa0cebc` | 筛选条 label 统一左置                            | §4.6（本轮新发现）               |

复现验收（1440×900 与 1374×780 两档视口，浅色与深色主题）：

- 侧栏高度恒等于视口高度（900/900，折叠态 900×64），内容区 56→900 铺满，
  长页面在内容区内滚动且末行可达、侧栏不随动；375px 窄屏无横向溢出。
- 实体类型详情页头出现「编辑」入口，基本信息（标签/定义）可改；
  关系类型草稿行出现「发布」，发布后状态由 DRAFT 变 PUBLISHED（v0 → v1）；
  业务域详情出现「编辑」，成员新增出现「跨域引用」勾选框。
- 四个业务表单空提交时为「必填星号 + 字段下方内联报错 + 零写入请求」。
- 本体设计器顶部工具条与「选择本体」下拉完整可见（裁剪链为空）；
  全屏页不再用负边距顶留白，改由路由 `meta.fullBleed` 去掉内容区留白。
- 统计卡激活态由 14px 扩散光晕改为 1px 实描边，不再压到页头说明文字。
- 关系类型/实体类型/标准条款三张表补 `scroll-x` 与列 `minWidth`，
  1080px 下「名称」列由 53px 恢复到 186px，表格在容器内横向滚动、页面无横向滚动条。
- 未迁移的库上请求 `/domains` 由纯文本 500 变为
  `{"code":"KG.DATABASE_ERROR","params":{"reason":"OperationalError"}}`，
  界面提示「请执行数据库迁移（alembic upgrade head）」。
- 本体库列表可用：侧栏「本体 → 本体库」出现；空态与页头都有「新建本体」；
  新建抽屉空提交零写入请求；创建后跳 `/ontology/designer?ontology=<id>`
  且设计器下拉已选中该本体；列表出现该行（草稿 / v0 / 设计器 / 发布）。
- 全站筛选条（样例预览、用户管理、操作日志、规则库、装配模板、标准条款、
  枚举字典、实体实例、来源证据、图谱浏览、实体类型库、关系类型库）的
  label 与控件均为「标签在左 + 同一行」，页面无横向滚动条。

开发库 `server/knowledge.db` 已从 `0010_ontology_rule_ids` 升级到
`0011_aggregate_edit_revision`（缺 `business_domain.edit_revision`、
`ontology.edit_revision`、`mapping.edit_revision` 三列，正是业务域页、
本体设计器页与映射向导报 500 的原因）。迁移前已备份为
`server/knowledge.db.bak-<时间戳>`，账号、业务域与资源数据均完整保留。

**仍未处理**：B1（正文字号 14px vs 设计稿 13px —— 两份设计来源口径冲突，
见 §3 B1）、B2（紫色 AI 轴与 AI 辅助入口）、B3/B4/B5（统计条第四项、
业务域筛选、属性/关系/更新时间列）、A2/A3（侧栏底部用户区、顶栏全局搜索）、
A4（侧栏/顶栏尺寸）、B6（大表格虚拟滚动）、D2/D3/D5（各资源删除能力）、
D8（业务域树形）、D9（命名空间管理界面）、D10（角色管理只读）、
D12（实体详情三个空页签与三张侧栏卡片）。

---

## 2. 整体框架布局问题（重点）

### A1 · 左侧导航栏未实现自适应高度 —— 已定位根因

**现象**：侧栏背景色块高度随页面内容变化，短页面上侧栏只覆盖半屏，下方露出页面底色，形成明显横向断层（见 `07-system-users` 实测：侧栏 462px，视口 900px）。

**实测数据**（1440×900 视口）：

| 页面       | 侧栏高度  | 页面内容高度 |
| ---------- | --------- | ------------ |
| 抽取运行   | **422px** | 900px        |
| 系统/用户  | 462px     | 900px        |
| 数据目录   | 462px     | 900px        |
| 业务域     | 502px     | 900px        |
| 实体详情   | 513px     | 900px        |
| 本体设计器 | 852px     | 900px        |
| 审计日志   | 1327px    | 1327px       |

结论：**侧栏高度跟随内容高度，而非视口高度**。内容比视口短时侧栏收缩（最严重时只占 47%），内容比视口长时才被撑开。

**根因（受控实验证实）**：`layout/AdminLayout.vue:34-36`

```css
.admin-layout {
  min-height: 100vh;
} /* ← 用了 min-height，不是 height */
```

naive-ui 的 `NLayout` 会在根元素与内容之间插入一层 `.n-layout-scroll-container`，其样式为 `height: 100%`。因为外层 `.admin-layout` 的 `height` 仍是 `auto`（只有 `min-height`），**百分比高度无法解析**，该滚动容器退回 `auto`（即内容高度），侧栏作为它的 flex 子项随之收缩。

注入样式前后对照实验（同一页面、同一视口）：

| 条件                                | 侧栏高度  | 滚动容器高度 | 外层高度 |
| ----------------------------------- | --------- | ------------ | -------- |
| 现状（`min-height: 100vh`）         | 462px     | 462px        | 900px    |
| 改为 `height: 100vh; min-height: 0` | **900px** | **900px**    | 900px    |

**修复建议**：把 `.admin-layout` 改为 `height: 100vh`（保留内容区内部滚动），或等价地在 `.n-layout-sider` 上显式 `height: 100vh`。两种改法实测均使侧栏高度等于视口高度。

### A6 · 内容区不撑满视口，底部大片空白

同 A1 根因：`.content`（`AdminLayout.vue:40-44`）作为滚动容器子项，高度同样塌陷为内容高度，因此内容卡片下方始终留出与视口等宽的空白带。A1 修复后此问题一并解决。

### A2 · 侧栏缺少底部用户区

设计稿 `design/02-ontology.html` 中侧栏为三段式：`.brand`（54px）+ `.nav`（`flex:1`）+ `.siderfoot`（底部头像 + 用户名 + 角色）。实现 `layout/components/AppSider.vue` 只有 brand + 菜单，用户信息被放到顶栏 `UserDropdown`。侧栏底部因此空置，也不符合设计稿的信息层级。

### A3 · 顶栏缺少全局搜索

设计稿 02/03/04/05/06 每屏顶栏都有 `.search`（"搜索名称、IRI 或属性" + `⌘K` 提示）。实现 `layout/components/AppHeader.vue:19-58` 只有折叠按钮、面包屑、语言、主题、用户菜单，**无全局搜索入口**。

### A4 · 侧栏/顶栏尺寸与设计稿不一致

| 项       | 设计稿 | 实现                      |
| -------- | ------ | ------------------------- |
| 侧栏宽度 | 212px  | 220px（`tokens.css:109`） |
| 顶栏高度 | 54px   | 56px（`tokens.css:111`）  |
| 折叠宽度 | —      | 64px                      |

差异不大，但属于"对照设计稿不一致"的事实，建议统一。

### A5 · 设计器全屏画布与高度链耦合

`views/ontology/Designer.vue:916-921` 用 `height: calc(100vh - var(--header-height) - var(--space-5) * 2)` 配合 `margin: calc(var(--space-5) * -1)` 抵消内容区留白来"占满内容区"。该算法与 A1 的高度链强耦合，修复 A1 后需同步调整；且 `--space-5`、`--header-height` 任一变化都会让画布高度算错。

---

## 3. 视觉与设计系统问题

### B1 · 正文字号 14px ≠ 设计规定 13px

设计稿 `design/01-tokens.html` 第 06 节明确："body 13 / 400 … 深色中后台取 13px 以获得更高的信息密度"。实测 `document.body` 计算字号为 **14px**，与 `styles/tokens.css:98`（`--font-body: 14px`）和 `theme/naive.ts:32`（`fontSize: '14px'`）一致。全站信息密度低于设计稿。

**⚠️ 两份设计来源口径冲突，改前需拍板**：`docs/frontend-redesign-plan.zh-CN.md` §4.1 写的是
"正文 14px、行高 1.6，表格等数据密度场景 13px"，与设计稿的"正文 13px"相反。
按时间看设计稿（2026-09-23，32 屏）晚于改版计划（2026-09-22），应以后者为准；
但这是全局排版改动，会影响所有页面，故未擅自修改，留待确认。

### B2 · 紫色 AI 轴与 AI 辅助入口完全未实现（五大签名元素之一）

设计稿把「品牌双轴」列为设计语言核心：青蓝 `#4F8DF7` = 操作，紫罗兰 `#8B5CF6` = AI，并明确"见紫即知『机器给的』"；第 08 节把「AI 辅助入口」列为**五大签名元素之一**，要求出现 `AI 补全`、`推断缺失定义域`、`从样例推荐映射`、`生成规则草案` 等紫色按钮。

实测全仓 `var(--violet)` 只出现 4 处，且都不是 AI 语义：

- `layout/components/UserDropdown.vue:85` — 头像渐变
- `views/datasources/DataCatalog.vue:1095/1100/1250` — 结构变更 diff 标记

**没有任何一个页面存在 AI 辅助入口**。`tokens.css:40-41/148-149` 定义了 `--violet` / `--violet-soft`，但没有任何消费方。这是设计系统层面最大的缺口。

### B3 · 实体类型统计条第四项与设计不符

设计稿 `design/02-ontology.html` 统计条为：`实体类型总数 / 已发布 / 草稿未发布 / 校验违反`。
实现 `views/ontology/EntityTypes.vue:40` 为 `['PUBLISHED','DRAFT','ARCHIVED']`，第四项是**「归档」**，缺设计的「**校验违反**」维度（该维度在后端 `validation` 模块已有数据，未接入）。

### B4 · 列表页筛选与视图能力少于设计稿

设计稿实体类型列表工具区：`全部业务域` 下拉 + `全部状态` 下拉 + `表格/卡片/图谱` 三段切换 + `AI 补全` + `新建类型`。
实现 `EntityTypes.vue:206-224`：只有一个搜索框 + `表格/卡片` 两段切换。缺 **业务域筛选**、**图谱视图**、**AI 补全**（状态筛选由统计条点击代替，可接受）。

### B5 · 实体类型列表列信息少于设计稿

| 设计稿列     | 实现列（`EntityTypes.vue:65-105`） |
| ------------ | ---------------------------------- |
| 名称         | ✅ 显示名                          |
| IRI          | ✅ IRI                             |
| **属性数**   | ❌ 缺                              |
| **关系数**   | ❌ 缺                              |
| 状态         | ✅ 状态                            |
| **更新时间** | ❌ 缺（改为显示版本号 v0）         |
| —            | ➕ 版本（设计稿没有）              |
| 操作         | ✅ 仅「编辑」                      |

### B6 · 大表格未启用虚拟滚动

设计稿 §5.4 要求"大表格与图谱列表虚拟滚动"。实测 `virtual-scroll` 只出现在 3 个图谱组件（`GraphEntities.vue:103`、`components/EvidenceTable.vue:62`、`components/GraphFactTable.vue:68`）。实体类型、关系类型、用户、审计日志、标准条款、枚举字典、规则、装配模板等**数据表全部未启用**。

### B7 · 页面样式不统一

同样是"列表页"，`EntityTypes.vue` / `RelationTypes.vue` / `Domains.vue` 用自定义 `.card` / `.toolbar` / `.seg` 手写样式；`AssemblyTemplates.vue` / `GovernanceRules.vue` / `StandardClauses.vue` 用 `NCard` + `NSpace` + `NFormItem` 做筛选条。同一种"筛选 + 表格"结构出现两套实现，间距、控件高度、标签位置都不一致。

---

## 4. 表单设计与交互问题

### C1 · 12 个业务页面表单无声明式校验

设计 §5.2 / §5.4 基线要求：**"label 关联输入框，错误信息靠近字段，blur 校验，提交必须有 loading 到成功或失败的反馈"**。

实测：只有 6 个账号/认证页使用 `:rules`（`Login` / `Register` / `ForgotPassword` / `ResetPassword` / `Profile` / `Security`）。以下 **12 个业务页面全部无 `:rules`、无 `path`、无字段级反馈**：

```
views/ontology/EntityTypes.vue          views/ontology/RelationTypes.vue
views/ontology/Domains.vue              views/ontology/EntityDetail.vue
views/datasources/DataSources.vue       views/governance/GovernanceRules.vue
views/governance/StandardClauses.vue    views/governance/EnumDictionaries.vue
views/governance/AssemblyTemplates.vue  views/governance/OntologyExport.vue
views/system/Users.vue                  views/system/AuditLogs.vue
```

DOM 实测（打开抽屉表单后）：

| 表单                     | 字段必填标记                                          | 字段级反馈节点 |
| ------------------------ | ----------------------------------------------------- | -------------- |
| 系统/用户管理 · 新建用户 | 5 个字段全部 `required: false`                        | 0 个           |
| 本体 · 新建实体类型      | 4 个字段全部 `required: false`                        | 0 个           |
| 本体 · 新建业务域        | 4 个字段全部 `required: false`                        | 0 个           |
| 治理 · 新建规则          | 8 个字段 `required: false`（label 里手工拼了 `" *"`） | 0 个           |

### C2 · 错误提示集中在表单底部，未靠近字段

实测：在"新建实体类型"抽屉内直接提交空表单后 —

- 字段级反馈节点：**0 个**
- 字段错误高亮（`n-form-item--error`）：**0 个**
- 唯一提示：抽屉底部一段文案 `"Machine name, namespace and Chinese label are required"`（`EntityTypes.vue:286` 的 `.create-error`）

即"整体报一句、字段不标红"，与设计要求的"错误信息靠近字段"直接冲突。同类实现见 `RelationTypes.vue:510/541`、`Domains.vue:484`、`EntityDetail.vue:506`。

### C3 · 抽屉主操作与取消按钮顺序相反

`EntityTypes.vue:287-294`、`RelationTypes.vue:511-518`、`Domains.vue:485-494` 均为「保存（主色）在左、取消在右」。中后台通行规范（以及本设计稿 `design/07-system-auth.html` 的按钮组）是「取消在左、主操作在右」，且 `AssemblyTemplates.vue:464-473` 自己用的是「取消在左、保存在右」——**站内自相矛盾**。

### C4 · 必填标记用手工字符串而非表单语义

`GovernanceRules.vue` 的表单把 `" *"` 直接拼进 label 文本（实测 label 值为 `"Rule identifier\n *"`），而 `required` 属性为 `false`。既没有必填样式，也没有参与校验，与 naive-ui 的表单语义脱节。

### C5 · 缺「表单页母版」的分组卡片与字段说明

设计 §5.2 定义表单页母版为"分组卡片、字段说明、blur 内联校验"。实测业务表单全部是**单列平铺 `NFormItem` 塞进抽屉**，没有分组卡片、没有字段说明文字（`Domains.vue` 新建域表单 4 个字段，除 IRI 的 placeholder 外无任何说明）。

### C6 · 筛选条 label 压在控件上方（已修 `aa0cebc`）

全站搜索/筛选条的标签都堆在控件上方：naive 的 `NFormItem` 默认 `label-placement="top"`，页面自绘的（`SamplePreview.vue` 的 `.field`、`GraphBrowse.vue` 的 `label`）也是纵向 `grid`。一行筛选要占两行高度，扫读时标签与控件对不上号。

涉及 12 个页面、两类写法，已统一为「标签在控件左侧 + 同一行」：

| 页面                           | 筛选字段                                |
| ------------------------------ | --------------------------------------- |
| 数据源 · 样例预览              | 数据源 / 模式 / 表 / 行数上限           |
| 数据源 · 数据目录              | 数据源 / 快照（本来就是左置，未改）     |
| 图谱 · 图谱浏览                | 搜索 / 邻域深度 / 结果集 ID / 隐藏类型  |
| 图谱 · 实体实例                | 搜索 / 排序                             |
| 图谱 · 来源证据                | IRI / 主体 / 谓词 / 客体                |
| 系统 · 用户管理                | 搜索 / 角色 / 状态                      |
| 系统 · 操作日志                | 搜索 / 操作                             |
| 治理 · 规则库                  | 搜索 / 规则来源                         |
| 治理 · 装配模板                | 搜索 / 模板类型；抽屉内 资源 / 固定版本 |
| 治理 · 标准条款                | 搜索（此前只有 placeholder）            |
| 治理 · 枚举字典                | 搜索 / 排序（此前只有 placeholder）     |
| 本体 · 实体类型库 / 关系类型库 | 搜索（此前只有 placeholder）            |

顺带补上**关系类型库缺失的搜索框**：后端 `/relations` 一直支持 `q`、`relationsApi.list` 也接受 `params`，但页面从未传过，列表无法按名称过滤（`RelationTypes.vue`）。

---

## 5. 增删改查完整性核查

### 5.1 前后端操作矩阵

| 资源     | 后端已实现                       | 前端 API                                            | 前端页面可执行                     | 缺口                                      |
| -------- | -------------------------------- | --------------------------------------------------- | ---------------------------------- | ----------------------------------------- |
| 实体类型 | GET/POST/PUT/publish             | list/get/create/update/publish                      | 列表：新建；详情：发布、改数据属性 | **❌ 不能编辑基本信息**；列表无发布/删除  |
| 关系类型 | GET/POST/PUT/**publish**         | list/get/create/update                              | 列表：新建、编辑                   | **❌ 前端未接 publish**；无详情页、无删除 |
| 业务域   | GET/POST/**PUT**/members/publish | list/create/members/add/remove/publishCheck/publish | 新建、成员增删、发布               | **❌ 前端未接 update**；无删除            |
| 本体     | GET/POST/PUT/refs/publish        | 全                                                  | 设计器可装配/发布                  | 无删除                                    |
| 命名空间 | GET/POST/DELETE                  | list/create/remove                                  | **无任何页面**                     | 命名空间管理无 UI                         |
| 数据源   | GET/POST/DELETE/test             | list/get/create/testConnection/remove/preview       | 新建、删除、测试连接               | 无编辑（后端契约亦无 PUT）                |
| 治理规则 | 全 CRUD + test                   | 全                                                  | 全                                 | —                                         |
| 标准条款 | 全 CRUD                          | 全                                                  | 全                                 | —                                         |
| 枚举字典 | 全 CRUD + revisions              | 全                                                  | 全                                 | —                                         |
| 装配模板 | 全 CRUD + copy/instantiate       | 全                                                  | 全                                 | —                                         |
| 用户     | GET/POST/PATCH                   | 全                                                  | 建号、改角色/状态                  | 无删除（契约本身无）                      |
| 角色     | GET                              | list                                                | 只读                               | 设计稿「角色管理」仅有只读列表            |
| 审计日志 | GET                              | auditLogs                                           | 只读                               | 符合设计                                  |

### 5.2 D1 · 实体类型编辑功能缺失（用户点名项，已证实）

**位置**：`views/ontology/EntityDetail.vue:417-427`

```vue
<template #actions>
  <n-button v-if="data && isDraft" type="primary" ... @click="handlePublish">
    {{ t('common.publish') }}
  </n-button>
</template>
```

详情页页头**只有「发布」一个按钮**。对照设计稿 `design/02-ontology.html` 第 02 屏，页头应有三个操作：`影响面扫描`、**`编辑`**、`发布新版本`。

代码层面证实：`EntityDetail.vue` 里 `entityTypesApi.update` **只被 `saveProperties()`（第 228 行）调用**，且 payload 固定为 `{ data_props, if_match, edit_revision }` —— **没有任何入口可以修改 `name` / `label_i18n` / `definition_i18n`**。后端 `PUT /entity-types/{id}` 支持完整更新，属前端未实现。

结论：**实体类型一旦创建，其名称、中文/英文标签、定义永久不可修改**，与用户判断一致。

### 5.3 D4 · 关系类型无法发布（工作流断链）

**位置**：`api/relations.ts:17-22`

```ts
export const relationsApi = {
  list: ..., get: ..., create: ..., update: ...,
}   // ← 缺 publish
```

后端 `relations.py:145` 有 `POST /relations/{relation_id}/publish`，前端未封装。`RelationTypes.vue` 列表页与编辑抽屉都没有发布入口，也**没有关系类型详情页**（`router/index.ts` 中无 relation detail 路由）。因此**草稿状态的关系类型在界面上永远无法发布**，后续本体装配与映射无法引用。这是 M3 主流程的断点。

### 5.4 D6 / D7 · 业务域

- **无编辑**：`api/domains.ts` 未封装 `PUT /domains/{id}`（后端 `domains.py:62` 已实现）。界面上无法修改业务域的名称/标签/定义。
- **「引用」角色不可达**：`Domains.vue:234-236`

  ```ts
  const updated = await updateDomain(
    (id, revision) => domainsApi.addMember(id, resourceId, false, revision), // ← as_ref 恒为 false
  )
  ```

  成员表里渲染了 `引用成员 / 核心成员` 两种角色（`Domains.vue:432-434`），但新增成员时 `as_ref` 硬编码 `false`，用户**永远无法把成员设为"引用"角色**，设计要求的"跨域引用"语义在 UI 上不可表达。

- **树形结构未实现**：设计稿要求业务域为 `n-tree` 懒加载 + 成员抽屉；实现为平铺列表 + 内嵌表格，代码注释明确写"业务域当前是平铺的（无父子），所以用列表而非树"（`Domains.vue:317`）。设计稿的业务域目录树与"维护责任域唯一"检查未落地。

### 5.5 D12 · 实体详情页三个页签是空占位

**位置**：`EntityDetail.vue:483-491`

```vue
<n-tab-pane name="relations" :tab="t('entityType.relations')"><n-empty .../></n-tab-pane>
<n-tab-pane name="rules" :tab="t('entityType.rules')"><n-empty .../></n-tab-pane>
<n-tab-pane name="references" :tab="t('entityType.references')"><n-empty .../></n-tab-pane>
```

「关联关系」「规则」「引用与版本」三个页签恒为空。设计稿要求分别展示：关联关系（含计数 5）、规则（含计数 3）、引用与版本（引用面统计 + 版本历史）。同时设计稿右侧栏的「继承链可视化」「校验状态（A03/A07/A08 四态）」「引用面」三张卡片全部缺失——`EntityDetail.vue:477-482` 的"类型层级"页签只把 `parent_ids` 渲染成一排 tag。

`implementation-plan.zh-CN.md` 第 4.2.1 节第 4 项明确要求该页为"六页签（基本信息/数据属性/类型层级/关联关系/规则/引用与版本）"，页签骨架在，内容未实现。

### 5.6 其他增删改查缺口

- **实体类型无删除**：后端与前端均无 DELETE（契约缺口）。列表操作列（`EntityTypes.vue:94-104`）只有「编辑」。
- **关系类型无删除**、**业务域无删除**、**本体无删除**：同上。
- **命名空间无管理界面**：`api/namespaces.ts` 有 `create` / `remove`，但全仓无任何视图调用（`EntityTypes.vue` / `RelationTypes.vue` 只调 `list` 用于下拉选项）。后端 CRUD 已就绪，前端零入口。
- **数据源无编辑**：`DataSources.vue` 只有新建/删除/测试连接；后端 `datasources.py` 也只有 GET/POST/DELETE，属**契约层缺口**（创建后连接信息不可修改）。
- **用户无删除**：`auth.ts` 有 `createUser` / `updateUser` / `users`，无删除；后端 `accounts.py` 也无 DELETE。用户只能禁用不能删除。

### 5.7 D13 · 本体没有列表页，也没有新建入口（已修 `8e818e6`）

**位置**：`api/ontology.ts` 的 `create`、`views/ontology/Designer.vue` 的空态

`ontologyApi.create` 在 API 层一直存在，但**从未被任何页面调用**（`git log -S "ontologyApi.create" -- web/src` 返回空，即从未调用过）。同时：

- 侧栏「本体」分组只有 实体类型库 / 关系类型库 / 业务域 / 本体设计器，**没有本体列表**；
- 设计器的空态文案写着「还没有本体。先在『装配模板』里选一个模板，**或直接创建一个本体**」，
  但页面上**没有任何新建入口**——属于 DoD 里「只弹提示不干活」的空话；
- 唯一的创建路径是绕到「治理 → 装配模板 → 实例化」。

对照设计稿 `design/02-ontology.html` 的 5 屏（实体类型 / 类型详情 / 关系类型 / 业务域 / 本体设计器），
设计稿本身也没有独立的本体列表屏，因此这一项是**功能缺口**而非实现走样。

修复：新增 `views/ontology/Ontologies.vue` 本体库列表（搜索 / 名称 / IRI / 状态 / 版本号 /
设计器 / 发布，空态带新建按钮）+ 新建本体抽屉（字段级校验）；侧栏「本体」分组首位加「本体库」；
设计器支持 `?ontology=<id>` 定位，空态补「新建本体」按钮并改指向本体库。

---

## 6. 影响验收的非前端问题

### 6.1 开发库未迁移，两个页面直接 500

`server/knowledge.db` 缺 `business_domain.edit_revision` 列（迁移 `0011_aggregate_edit_revision` 未执行）。未迁移时：

```
GET /api/v1/domains    → 500  sqlalchemy.exc.OperationalError:
                              no such column: business_domain.edit_revision
GET /api/v1/ontologies → 500
```

前端表现为业务域页整页报错（`Unknown error: ERR_BAD_RESPONSE`）、本体设计器不可用。`docs/architecture-audit.zh-CN.md` 已写明"现有数据库启用新代码前需要执行 Alembic 升级"，但**没有任何启动检查或友好提示**，开发者拉下代码直接跑就会撞上。

附带问题：错误提示直接暴露 axios 内部字符串 `Unknown error: ERR_BAD_RESPONSE`（`useApiError` 未兜底非业务错误），违反"错误码 + 双语翻译"的硬规则。

### 6.2 首屏语言按浏览器判定

`i18n/index.ts:10-19`：无 `kg-locale` 时按 `navigator.language` 判定。实测英文环境浏览器首屏即为英文界面，与 `README.md`「默认中文，支持英文」的表述不一致（`frontend-redesign-plan.zh-CN.md` §3.2 允许此回退，但与 README 口径冲突，需二选一）。

---

## 7. 修复优先级建议

**第一批（阻断主流程，必须修）**

1. A1/A6 侧栏与内容区高度：`AdminLayout.vue:34` 改 `min-height: 100vh` → `height: 100vh`（已实测验证，改动一行）。
2. D1 实体类型基本信息编辑：详情页页头补「编辑」入口 + 基本信息表单，调用已有的 `PUT /entity-types/{id}`。
3. D4 关系类型发布：`api/relations.ts` 补 `publish`，列表/编辑处补发布入口。
4. D6 业务域编辑：`api/domains.ts` 补 `update`，详情页补编辑入口。
5. §6.1 迁移：补启动时的 schema 版本校验或文档化的前置步骤；`useApiError` 兜底网络级错误。

**第二批（设计一致性，影响观感）**

6. C1/C2/C5 表单：把 12 个业务页表单接入 `:rules` + `path`，字段级反馈，补齐必填标记；统一为"取消在左、主操作在右"。
7. B1 正文字号统一到 13px。
8. B2 AI 辅助入口：至少在实体类型、关系类型、映射向导三处按设计稿补紫色 AI 入口（或明确决策不做，并同步修订设计稿）。
9. B3/B4/B5 实体类型列表：统计条第四项改「校验违反」，补业务域筛选、属性/关系/更新时间列。
10. A2/A3 侧栏底部用户区、顶栏全局搜索。
11. D12 实体详情三个空页签 + 继承链/校验状态/引用面卡片。

**第三批（规范与体验细节）**

12. A4 侧栏 212px / 顶栏 54px 对齐设计稿；A5 设计器高度算法解耦。
13. B6 大表格虚拟滚动；B7 统一列表页样式（择一实现）。
14. D9 命名空间管理界面；D7 成员"引用"角色开关；D8 业务域树形结构。
15. 5.6 各资源删除能力（需后端契约同步补齐）。

---

## 8. 核查边界

- 本报告为**前端实现与原设计的一致性核查**，不含像素级视觉审查（颜色/间距的逐点比对未做）。
- 未覆盖：后端领域逻辑正确性、语义引擎输出、Playwright 既有用例是否失效。
- §5 的"无删除"类结论中，实体类型/关系类型/业务域/本体/用户的删除能力在**后端契约层即不存在**，属产品范围问题而非前端遗漏，已单独标注。
- 实测环境：macOS + Chromium 1440×900（另有 375px 窄屏未在本轮覆盖，`frontend-redesign-plan` 声称已由 Playwright 覆盖）。
