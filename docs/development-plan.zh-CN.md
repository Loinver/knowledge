# 知识中台（Knowledge Middle Platform）· 开源项目开发计划

> 编制：2026-09-21
> 仓库：**https://github.com/Loinver/knowledge**（main 分支，已含 MIT LICENSE）
> 输入：`demo/知识中台Demo.html`（19 路由 / 6 一级菜单，单文件可运行）、`demo/知识中台功能清单与优先级.xlsx`（47 项功能）、`demo/知识中台开发功能清单与分阶段计划.md`（S0–S5 / H-M-L 编号）、`demo/tests/*.cjs`、`GB/T 48000.3—2026 本体建模标准.pdf`
> 目标：以 demo 已验证的**设计结论与交互方案**为蓝本，重建一个**可持久化、可真实执行、可开源协作**的完整知识中台。MIT 协议，默认中文，支持英文。
> 全文沿用 demo 的功能编号（H-/M-/L-）与验收编号（A01–A20），可直接作为需求单 / issue 编号前缀。

---

## 0. 一句话结论

**前端 Vue 3，后端 Python FastAPI（语义栈 rdflib + pySHACL + owlrl），单一仓库 monorepo、单命令启动、Docker 一体部署；i18n 从第一天起做，且必须做到"领域内容双语"而不只是"界面双语"。**
第一个可发布版本（v0.1.0 / M3）的范围 = demo 的 P0 共 22 项功能 + i18n + 开源化基建。全部 47 项做到 v1.0。

---

## 1. 对 demo 的阅读结论

### 1.1 已验证、可直接复用的资产（不要重写）

| 资产                                                                | 位置                                   | 复用方式                                        |
| ------------------------------------------------------------------- | -------------------------------------- | ----------------------------------------------- |
| 6 大一级菜单 / 19 个路由的信息架构                                  | `NAV`（2081 行）                       | 直接作为前端路由与目录结构                      |
| 实体类型 / 关系 / 业务域 / 本体 / 映射五大资源模型                  | `TYPE` `REL` `DOMAIN` `ONTO` `MAPPING` | 直接转成数据库表 + Pydantic 模型                |
| 抽取引擎四阶段（实体→关系→规则→隔离）与统计口径                     | `runExtraction()`                      | 逻辑整体移植，数据源换成真实连接器              |
| 关系映射三模式（外键 / 中间表 / 关联表）                            | `mp.relMaps`                           | 配置结构直接沿用                                |
| 资产层 8 项校验 A01–A08 与**四态输出**（通过/违反/不适用/未执行）   | `validateOntology()`                   | 检查逻辑保留，执行换成真实 SHACL + OWL          |
| 图谱布局算法（分区、贝塞尔折行、标签贪心避让、按 scope 存拖拽位置） | `kgData()` / 画布相关                  | 移植为 SVG 自绘组件，算法直接搬                 |
| 5 步映射向导 + 图谱/表格双视图                                      | `pageMapping()`                        | 交互方案直接沿用                                |
| 回归断言                                                            | `tests/*.cjs`                          | 迁移为 pytest + Vitest 断言                     |
| 样例数据（含"同一对实体两条参与记录"）                              | `TABLES`                               | 转成 `samples/seed.sql`，这是最值钱的可复用资产 |

### 1.2 必须重写（demo 的硬边界，不要在 demo 上"加个后端"）

1. **全部数据层**：内存对象 → 元数据库（PostgreSQL），刷新即重置的边界必须消除。
2. **校验执行**：演示子集 → 真实 SHACL 报告 + OWL 推理。A08（OWL 一致性）在 demo 里被硬编码为"未执行"，这是诚实做法，但正式版必须能真跑。
3. **数据来源**：内置模拟表 → 真实只读连接器（凭据后端托管）。
4. **并发与治理**：修订号乐观锁、发布冻结、权限、审计。
5. **导出**：文本预览 → 可被独立解析器回读的真实序列化（Turtle / JSON-LD / SHACL）。导入缺失，需新建。
6. **i18n**：demo 全中文硬编码，需全量改造。

### 1.3 demo 里三条必须继承的"产品哲学"

- **四态校验**：未执行 ≠ 通过。任何"没跑就显示绿"的行为都是合规事故。
- **版本冻结**：本体发布冻结资源版本，映射发布冻结本体版本，上游改版不静默影响下游。
- **关系属性不塞进三元组**：带属性关系走关联实体 + 端点角色，同一对实体两次业务关系分别保存，不被去重。

---

## 2. 开源项目定位与仓库设计

### 2.1 定位

一个**可自托管的企业级语义建模与知识抽取平台**：从本体建模 → 数据接入 → 映射配置 → 抽取执行 → 图谱与证据追溯，端到端闭环，并可对 GB/T 48000.3—2026 出具符合性校验结论。

差异化价值（README 卖点）：

- 端到端闭环（不是又一个本体编辑器，也不是又一个图谱可视化工具）
- 事实级证据追溯（每条三元组可反查到表·行键·字段·运行批次）
- 诚实校验（四态输出，未执行就是未执行）
- 中英双语的**领域语义**（不只是界面翻译）

### 2.2 命名（待定，建议三选一）

| 候选            | 含义       | 备注                                       |
| --------------- | ---------- | ------------------------------------------ |
| `SemanticForge` | 语义锻造   | 强调建模与抽取，GitHub 名 `semantic-forge` |
| `KnowledgeHub`  | 知识中枢   | 直白，但重名多                             |
| `OntoFlow`      | 本体流水线 | 强调端到端流程                             |

### 2.3 仓库结构（monorepo，前后端一体）

```
semantic-forge/
├── LICENSE                  # MIT
├── NOTICE                   # 第三方依赖许可归集
├── README.md                # 中文主读本
├── README.en.md             # 英文主读本
├── CONTRIBUTING.md / CODE_OF_CONDUCT.md / SECURITY.md / CHANGELOG.md
├── .github/                 # ISSUE/PR 模板、CI workflows、discussion 分类
├── server/                  # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/          # 路由：types/relations/domains/ontologies/
│   │   │                    #       sources/catalog/mappings/runs/graphs/evidence/reports/rules
│   │   ├── domain/          # 领域服务（不依赖 Web 框架，可单测）
│   │   ├── semantics/       # 语义适配层：rdflib / pySHACL / owlrl（可替换实现）
│   │   ├── connectors/      # 只读数据源连接器
│   │   ├── models/          # SQLAlchemy ORM
│   │   ├── schemas/         # Pydantic v2
│   │   └── core/            # 配置、错误码、加密、日志
│   ├── migrations/          # Alembic
│   ├── tests/               # pytest
│   └── pyproject.toml
├── web/                     # Vue 3 前端
│   ├── src/
│   │   ├── api/             # 自动生成的 OpenAPI 客户端
│   │   ├── views/           # 19 个路由页面
│   │   ├── components/      # 画布、图谱、向导、抽屉等
│   │   ├── locales/         # zh-CN / en-US
│   │   ├── stores/          # Pinia
│   │   └── router/
│   └── package.json
├── samples/                 # 样例源库 seed（enterprise_demo）+ docker-compose
├── docs/                    # 设计文档、ADR、标准对照表
└── docker-compose.yml       # 一体启动（server + web(nginx) + postgres）
```

**启动方式**：`make dev`（后端 uvicorn :8000 + 前端 vite :5173，前端代理 /api）；`make up`（docker compose 单机一体，:8080 单端口）；`make seed`（灌入样例源库 + 内置本体与映射，10 分钟跑通全流程）。

### 2.4 合规红线（写进 CONTRIBUTING，CI 检查）

1. **依赖准入**：只允许 MIT / BSD / Apache-2.0 / PSF 系许可；**禁止引入 GPL/AGPL/LGPL 依赖**（尤其图数据库客户端与某些 NLP 库）。CI 用 `pip-licenses` 卡一道。
2. **标准文本**：GB/T 48000.3—2026 正文**不入库**。仓库只保留「条款编号 + 自撰的简短描述性引用」（如 `6.2.2 → 标准实体类`），标准 PDF 不放进 `samples/`。这是版权与标准出版权的硬约束。
3. **示例数据脱敏**：demo 已使用 `example.org`、`91310000DEMA000001` 之类明显虚构值，可直接继承；真实客户数据不得入库。
4. **DCO**：贡献者签署 `Signed-off-by`（比 CLA 轻量，降低个人贡献门槛）。

---

## 3. 技术选型

### 3.1 前端

| 项          | 选择                                                                                      | 理由                                                                                          |
| ----------- | ----------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| 框架        | **Vue 3 + TypeScript + Vite**                                                             | 用户指定；Vite 生态与中文社区成熟                                                             |
| 状态        | Pinia                                                                                     | 轻量，替代 demo 的全局 `S`                                                                    |
| 路由        | Vue Router 4（hash/history 兼容 demo 的 `#/menu/sub/param`）                              | 与 demo 路由结构一一对应                                                                      |
| **UI 库**   | **Naive UI**（备选 Element Plus，见 §3.1.1）                                              | 表格与 TS 类型是本项目最高权重项                                                              |
| i18n        | **vue-i18n v9**                                                                           | 见 §5                                                                                         |
| 画布 / 图谱 | **自绘 SVG + D3-force 辅助**                                                              | demo 的布局算法已验证；第三方流程图库很难满足"关联实体 + 派生边 + 多条事实弯曲"的语义表达需求 |
| 图表        | ECharts（仅工作台统计）                                                                   | 轻量使用                                                                                      |
| 样式        | UI 库主题变量 + 自定义 CSS 变量（对齐 demo 的 `--pri:#315ee7` 体系）；**不引入 Tailwind** | 避免 preflight 与组件库样式打架                                                               |

#### 3.1.1 UI 框架选型（本项目的真实权重）

**先明确这个项目的 UI 需求画像**，否则选型会退化成"哪个库流行"：

| 需求                | 出现位置                                                      | 对 UI 库的要求                                    |
| ------------------- | ------------------------------------------------------------- | ------------------------------------------------- |
| 超密集表格          | 实体实例、来源证据、隔离清单、元数据字段目录（H-21/40/41/42） | **虚拟滚动是刚需**（M-13），且要树形 + 行内可编辑 |
| 数据目录树          | 业务域目录树、库/表/字段四级下钻（H-10/21）                   | 树组件 + 懒加载                                   |
| 六页签详情抽屉      | 实体类型详情（H-11）                                          | Tabs + Drawer + 表单校验                          |
| 5 步向导            | 映射方案（H-30）                                              | Steps + 分步表单                                  |
| 全页可拖拽 SVG 画布 | 本体设计器（H-13）、图谱浏览（H-40）、映射图谱视图（H-30）    | **UI 库帮不上，全部自绘**；只要求容器/面板不干扰  |
| 语义化状态标签      | 四态（通过/违反/不适用/未执行）、草稿/已发布                  | Tag + 颜色语义固定                                |
| 主题色对齐 demo     | 全局                                                          | 需要低成本改主色与圆角/线宽                       |

**结论：本项目 UI 库的真实权重是「表格质量 > TS 类型 > 主题可定制 > 组件齐全度 > 社区规模」。** 画布和图谱是自绘，与 UI 库无关；真正天天用的是表格、表单、抽屉、树。

**候选对比（Vue 3 生态，全部 MIT）**

| 维度                       | **Naive UI**                 | Element Plus                         | Ant Design Vue     | Vuetify              | Tailwind + shadcn-vue     |
| -------------------------- | ---------------------------- | ------------------------------------ | ------------------ | -------------------- | ------------------------- |
| TS 类型质量                | **高（TS 源码编写）**        | 中（历史包袱）                       | 中偏弱             | 中                   | 高                        |
| 表格（虚拟滚动/树/可编辑） | **一体化 data-table**        | el-table 与 el-table-v2 **API 分裂** | 有虚表，树支持一般 | labs 中不稳          | 需自建 TanStack Table     |
| 主题定制                   | **运行时 themeOverrides**    | SCSS 变量（编译期）                  | less token         | SASS                 | 完全掌控                  |
| 内置 locale（zh/en）       | 有（zhCN/enUS + dateLocale） | 有（40+ 语言）                       | 有                 | 有                   | 无，自理                  |
| 组件齐全度                 | 高（略少）                   | **最高**                             | 高                 | 高                   | 低（自建）                |
| 中文文档/社区规模          | 好                           | **最强**                             | 好                 | 一般（英文为主）     | 英文                      |
| 默认观感与本项目匹配       | **紧凑克制，接近 demo**      | 偏"圆润蓝"通用后台                   | antd 味重          | Material，信息密度低 | 自定                      |
| 维护主体                   | 主要 1 人（07akioni）        | 团队+社区                            | 社区               | 团队                 | 社区                      |
| 额外基建成本               | 0                            | 0                                    | 0                  | 0                    | **1.5–2 周 + 持续自维护** |

**推荐：Naive UI。** 三条决定性理由：

1. **表格是本项目最高频组件**，且 M-13 明确要求大数据量分级展示。Naive UI 的 `n-data-table` 把虚拟滚动、树形数据、可编辑单元格放在**同一套 API** 里；Element Plus 的 `el-table`（功能全但不支持虚表）与 `el-table-v2`（支持虚表但 API 不同）是两套东西，后期从实例列表切到虚表意味着重写。
2. **端到端 TS 类型链路的最后一环**。本项目前端类型全部由 OpenAPI 生成，类型链路的价值取决于最弱一环；Naive UI 由 TypeScript 编写，类型定义质量明显更好，能显著减少 `as any` 与类型断言。
3. **运行时主题定制**。demo 的视觉语言（`#315ee7` 主色、细线、小圆角、高信息密度）需要精细覆盖；`themeOverrides` 可以在运行时改，也能按 zh/en 或明暗切换，不需要 SCSS 编译链。且 Naive UI 默认观感就是"紧凑克制"，比 Element Plus 的默认样式更接近 demo。

**为什么不选自建（Tailwind + shadcn-vue）**：视觉最可控、门面最漂亮，但 Table / Tree / Drawer / Tabs / Steps / 表单校验全部要自建并长期自维护。对 47 项功能、19 个路由的项目，这是**持续成本而非一次性成本**，会把 M1–M3 的精力从语义能力上挪走。语义能力才是本项目的护城河，UI 不是。

**为什么不选 Ant Design Vue / Vuetify**：ADV 的 Vue3 版本 TS 体验与节奏是长期被吐槽项；Vuetify 的 Material 风格与高信息密度的中台表格天然冲突。

**风险与缓解**

| 风险                    | 说明                     | 缓解                                                                                                                                                       |
| ----------------------- | ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Naive UI 主要由个人维护 | 长期演进依赖作者         | 对三个高频且可能变的组件做**薄封装**：`<KgTable>` `<KgTag>` `<KgDate>`（约半天工作），其余直接用原生组件；真要换库时改动面可控。不做全量封装——那是过度设计 |
| 个别组件缺失            | 如复杂穿梭框、组织架构图 | 本项目这类组件本来就要自绘（M-10 组织架构图）                                                                                                              |
| 与自绘 SVG 画布样式冲突 | 主题变量两套             | 统一在 `web/src/styles/tokens.css` 定义 CSS 变量，Naive UI 主题与 SVG 画布**共用同一份变量**                                                               |

**待确认**：若你更看重"团队接手门槛 / 中文资料密度 / 组件齐全度"，Element Plus 是完全可接受的次选，切换成本主要在表格 API 与主题覆盖方式（约 1 周）。建议在 M0 用一个真实页面（实体实例列表，含虚表 + 筛选 + 分页）做**两天验证**，再定稿。

### 3.2 后端（本次决策点）

**结论：Python 3.12 + FastAPI。**

| 层         | 选择                                                                                                                 | 说明                                                                |
| ---------- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Web 框架   | FastAPI + Pydantic v2                                                                                                | 自动生成 OpenAPI → 前端 TS 客户端自动生成，前后端契约不靠口头约定   |
| ORM / 迁移 | SQLAlchemy 2.0 + Alembic                                                                                             |                                                                     |
| 元数据库   | **PostgreSQL 16**（生产）/ SQLite（dev & 单文件演示）                                                                | 与被抽取的源库**物理分离**，这是硬约束                              |
| RDF        | **rdflib**                                                                                                           | Turtle / JSON-LD 解析与序列化、SPARQL 查询，BSD-3                   |
| SHACL      | **pySHACL**（基于 rdflib，W3C 标准 SHACL Core）                                                                      | 输出**真实校验报告**，不满足"只展示规则文本"的伪校验，Apache-2.0    |
| OWL 推理   | **owlrl**（RDFS+OWL Horst 扩展）作为内置最小集；**可选 Docker sidecar：Apache Jena + HermiT** 提供完整 OWL-DL 一致性 | A08 项：未接 sidecar 时如实标"未执行"，接入后转真实结论；能力可插拔 |
| 执行       | 首版：FastAPI 后台任务（asyncio + 运行记录落库 + 状态机）；S5：Celery + Redis                                        | 首轮单任务串行即可满足                                              |
| 凭据加密   | cryptography AES-GCM，密钥来自环境变量/KMS                                                                           | 凭据永不出后端                                                      |
| 连接器     | SQLAlchemy dialects：SQLite / MySQL / PostgreSQL（只读强制）                                                         | L-05 再扩 Hive/REST                                                 |

**为什么不是 Java + Spring Boot + Apache Jena**：Jena 的语义能力最完整（SHACL + HermiT 一站式），但（a）开发效率与前后端一体的迭代速度明显低于 Python；（b）开源项目贡献门槛更高；（c）本项目真正需要的 SHACL Core 与 OWL 一致性，pySHACL + owlrl 已覆盖，完整 OWL-DL 只在 S4 出具规范结论时才必需。
**折中方案**：把语义能力封装成 `app/semantics/` 的**适配层**（接口 `parse/serialize/validate/reason`），提供 `RdflibBackend` 与可选的 `JenaRemoteBackend`。这样既不牺牲 P0 效率，又给 S4 留出替换成完整推理器的口子——**只需换实现，不动业务代码**。

**为什么不是 Node/NestJS**：JS 侧没有稳定成熟的 SHACL 实现与 OWL 推理器，H-04 会变成自研，风险最高。

### 3.3 存储与规模

- 元数据库（PG）：资源、版本、映射、运行、报告。
- 图谱数据：首版用**关系表存三元组**（`graph_triple` + 索引）+ 实体属性 JSONB；**不要过早引入图数据库**。规模上限在 M3 实测后写入产品说明（诚实标注，如"10 万实体 / 50 万三元组内流畅"）。
- 文件/导出：本地卷 + 可选 S3 兼容存储（L-05）。

---

## 4. 前后端一体与契约

1. **单一真值源**：FastAPI 生成 `openapi.json` → CI 用 `openapi-typescript` 生成 `web/src/api/schema.d.ts` 与类型化客户端。禁止前端手写类型。
2. **错误契约**（i18n 友好）：后端**只返回错误码 + 结构化参数**，绝不返回中文句子。
   ```json
   {
     "code": "KG.REVISION_CONFLICT",
     "params": { "resource": "type:Employee", "expected": 7, "actual": 9 },
     "message": "Revision conflict"
   }
   ```
   前端按 `KG.REVISION_CONFLICT` 查 i18n 表渲染中文/英文。CI 校验前后端 key 集合一致。
3. **修订号并发控制**：所有写接口强制 `If-Match: <revision>`，冲突返回 `KG.REVISION_CONFLICT`（409）。
4. **四态与状态枚举**：用**枚举码**传输（`PASS/VIOLATION/NA/NOT_RUN`、`DRAFT/PUBLISHED`），前端翻译。禁止传中文状态串。

---

## 5. i18n 方案（重点，必须三层都做）

知识中台的 i18n 有个坑：只翻译界面，本体内容仍是中文，英文用户看到的是一个"英文外壳 + 中文内核"。所以分三层：

### L1 · 界面文案（vue-i18n）

- 默认 `zh-CN`，备选 `en-US`；切换存 localStorage，未设置时按 `Accept-Language` 回退。
- 所有文案走 `$t()`，组件内**禁止出现中文/英文硬编码字符串**，用 ESLint 规则（`vue-i18n/no-raw-text`）卡住。
- Element Plus 语言包、日期/数字格式化（`Intl`）同步切换。

### L2 · API 消息与枚举

- 如 §4：错误码 + 参数；状态/四态/严重度/关系模式等一律枚举码。
- 后端不翻译，前端翻译；`docs/i18n/message-codes.md` 作为码表单一真值源，CI 校验 zh/en 覆盖率 100%。

### L3 · 领域语义内容（本项目特有的关键层）

- 实体类型、数据属性、对象属性、业务域、规则、枚举字典的**标签与定义**必须支持 zh/en 双语。
  实现：资源表上 `label_i18n JSONB`（`{"zh-CN": "员工", "en-US": "Employee"}`）+ `definition_i18n JSONB`；`name`（英文机读名，如 `Employee`）**单值、全局唯一、不翻译**，IRI 由 `namespace + name` 推导。
- demo 现有数据里 `zh` 与 `name` 天然就是这套双轨（如 `{zh:'员工', name:'Employee'}`），**迁移时零成本**——只需把 `zh` 升级为 `label_i18n['zh-CN']`，`name` 直接作为英文标签的默认值。
- 导出：Turtle / JSON-LD 时按语言输出多语言字面量（`rdfs:label "员工"@zh-Hans, "Employee"@en`）。
- 编辑界面：双语字段同屏编辑，中文必填、英文可选（缺失时回退显示中文并在 UI 标注"未翻译"——与四态校验同源的诚实原则）。
- 命名空间前缀、IRI 模板**不翻译**。

### 落地时点

**M0 就要建立 L1/L2 骨架**（i18n 是横切能力，事后补会牵动全部组件，与 demo 文档里对 H-03 IRI 治理的判断同构）。L3 在 M1 随实体类型/关系库落地。

---

## 6. 元数据库设计（M0 交付核心）

沿用 demo 文档给出的 14 张表，分层落地：

**资源与版本层**

- `namespace`（prefix, iri, protected）
- `model_resource`（id, kind: ENTITY|DATATYPE_PROP|OBJECT_PROP|ASSOC, name 唯一, iri, label_i18n, definition_i18n, status, current_revision, created_at）
- `resource_revision`（resource_id, rev, payload JSONB, published_at, published_by, checksum）—— **资源不可变版本，发布即冻结**
- `resource_parent`（继承）、`resource_ref`（引用统计/更名影响面）

**业务域层**

- `business_domain` / `domain_revision` / `domain_member`（domain_id, resource_id, as_ref, owner_domain）

**本体装配层**

- `ontology` / `ontology_revision`（template, ref_domains[], ref_types[], rules[], resource_versions{} 钉住）/ `ontology_resource_ref` / `canvas_layout`（scope, positions JSONB，**不产生语义版本**）

**数据接入层**

- `datasource`（连接参数 + 凭据密文，浏览器只拿可展示字段）/ `metadata_snapshot`（库→schema→表/视图→字段，含类型/可空/PK/FK/注释 + 结构变更识别）

**映射层**

- `mapping` / `mapping_revision`（onto_version 冻结, entity_maps JSONB, rel_maps JSONB）/ `mapping_preview`

**执行与图谱层**

- `extraction_run`（status, cfg 快照, fingerprint, counts, started/finished）
- `graph_revision`（run_id, is_current, publishable）/ `entity_instance` / `graph_triple` / `derived_edge` / `fact_evidence`（subject, predicate, object, source_id, table, row_key, columns[], run_id, evidence_type）
- `quarantine`（隔离清单：表/源键/字段/原值/转换链/命中规则）
- `validation_report` / `validation_result`（四态 + 焦点节点 + 规则来源）

**治理层**（M4 起）

- `rule` / `enum_dict` / `assembly_template` / `audit_log`

**关键约束写进迁移脚本**：`model_resource.name` 唯一；`resource_revision` 只增不改；`graph_revision` 当前结果集唯一指针（`is_current` 部分唯一索引）；失败运行不得改写 `is_current`。

---

## 7. 分阶段计划

沿用 demo 的 S0–S5，重编号为对外里程碑 M0–M5，并把 i18n 与开源化前置。

### M0 · 基座 + 语义引擎 + i18n 骨架（3 周 / 单人 5 周）

**目标**：消灭"数据在内存、刷新即重置"，验证语义引擎能真跑，并把 i18n 骨架钉死。

交付：

1. 元数据库 schema + Alembic 迁移（§6）
2. FastAPI 骨架 + OpenAPI 契约 + 错误码体系 + 修订号并发控制（H-00/H-01/H-02）
3. 命名空间与 IRI 治理：IRI 生成、唯一性校验、**更名影响面扫描接口**（H-03）
4. 语义引擎 PoC（H-04）：`semantics/` 适配层 + rdflib 解析/序列化 + **一个真实 SHACL shape 跑出真实报告** + owlrl 最小推理；同时验证 Jena sidecar 可选路径
5. i18n L1/L2 骨架：vue-i18n、语言切换、错误码表、Element Plus 双语、ESLint 未翻译检查
6. CI 基线：GitHub Actions（ruff + mypy + pytest + eslint + vue-tsc + build + 许可证检查）
7. 开源化基建：LICENSE/NOTICE/CONTRIBUTING/PR-Issue 模板/DCO

**验收**：写一条资源→发布→重启进程→仍在；改名字→引用方（关系端点、域成员、本体引用、映射）同步；SHACL 报告为真实引擎产出（非硬编码）；界面切英文无中文残留（除领域内容外）。

### M1 · 语义资产闭环（5 周 / 单人 8 周）★ 主流程上半段

交付：H-10 业务域、H-11 实体类型库、H-12 关系类型库、H-13 本体装配与设计器、H-50 资产层校验（A01–A08）+ i18n L3 双语字段。

- 类型详情六页签（基本信息/数据属性/类型层级/关联关系/规则/引用与版本）
- 关系：定义域/值域/基数（注明约束方向）/逆关系/OWL 特征/关联实体模式生成
- 全页可拖拽画布（SVG 自绘，移植 demo 布局算法），**拖拽只改 `canvas_layout`，不产生语义版本**
- 校验 A01–A07 真实执行，A08 未接推理器时显示"未执行"

**覆盖主流程**：S1 建实体类型 → S2 建关系 → S3 组业务域 → S4 装配本体并发布
**验收**：A01–A06、A17

### M2 · 数据接入与映射（4 周 / 单人 7 周）★ 主流程中段

交付：H-20 数据源连接（后端持凭据、只读强制、测试连接、超时）、H-21 元数据采集与数据目录（四级下钻 + 结构快照 + 变更识别 + 反向引用）、H-22 受限样例预览、H-30 映射方案 5 步向导（图谱/表格双视图，未配置项图上可见）、H-31 映射编译与预览（字段四列实算、关系三模式、字段级错误定位）。
**关键交付物**：`samples/enterprise_demo` 样例库 + seed 脚本——必须覆盖**外键、中间表、带属性关联表**三类结构，且含**同一对实体两条参与记录**（直接沿用 demo 的 `pm_project_member` 7001/7003 设计）。

**覆盖**：S5 接入数据源 → S6 配置映射
**验收**：A10 A11 A12 A15 A18

### M3 · 抽取执行与图谱闭环（5 周 / 单人 8 周）★ P0 交付点

交付：H-32 抽取引擎四阶段（幂等）、H-33 图谱版本与结果集管理、H-40 图谱浏览、H-41 实体实例、H-42 来源证据追溯、H-51 实例校验报告（四态）、H-60 工作台。
**里程碑 M3 贯通测试（必须一次跑完整条链，8 步）**：

1. 从零建 3 个实体类型 + 2 个关系类型 → 全部发布、IRI 稳定
2. 组 1 个业务域 + 装配 1 个本体并发布 → 8 项校验无"违反"，A08 如实标"未执行"
3. 配 1 份映射（覆盖外键 + 中间表 + 关联表三模式）→ 预览字段级实算正确
4. 运行抽取 → 产出实体/关系/派生边/隔离清单，计数可复现
5. **重复运行** → 实体 IRI 集合、关系数、隔离数完全一致（幂等）
6. 制造失败运行（清空来源表）→ 判失败，**当前结果集不变**，可切回上一成功运行
7. 任取一条事实 → 反查到连接/表/行键/字段/运行批次
8. 隔离记录 → 定位到表/源键/字段/原值/转换链/命中规则

**验收**：A13 A14 A20；四项自动化回归断言（幂等 / 失败保护 / 结果集切换 / 证据追溯）
**产出**：打 tag `v0.1.0`，发布 Docker 镜像与在线 Demo（`make seed` 后 10 分钟走通）。

### M4 · 规范符合性与开源化收口（3 周 / 单人 5 周）

交付：M-01 规则库（来源可见：标准条款 / 企业规则）、M-02 核心模板逐项核对、M-03 标准资料（条款编号 + 自撰描述，**不抄正文**）、M-04 装配模板管理、M-05 枚举字典、M-06 本体导入 + 冲突预览、M-07 导出完善（可被独立解析器回读）、i18n 双语补齐与覆盖率 100%、README 中英双版、贡献指南、路线图公开。
**验收**：A07 A08 A09 A16 A19
**硬边界**：出具"符合 GB/T 48000.3"结论前，必须接入真实推理器并跑通 A08。在此之前不出具完整符合结论。
**产出**：`v1.0.0`

### M5 · 规模化与运营（滚动，6 周+）

按价值排序：M-08 任务契约 + M-09 取消运行 → L-01 增量（四要素：稳定水位/重放去重/删除标记/失败重试；水位只在成功提交后推进）→ L-02 调度 → M-11 权限基线 + M-12 审计 → M-13 大数据量分级展示 → M-10 图谱增强视图（组织架构图、邻接矩阵）→ L-03 文档抽取 / L-04 AI 辅助映射 / L-05 更多连接器 / L-06 跨源融合 / L-07 版本影响分析 / L-09 开放 API / L-11 语义问答。

---

## 8. 测试与 CI

| 层           | 工具                           | 内容                                                                  |
| ------------ | ------------------------------ | --------------------------------------------------------------------- |
| 后端单测     | pytest                         | 领域服务、IRI 重算、版本冻结、映射编译                                |
| 后端集成     | pytest + testcontainers(PG)    | 抽取幂等、失败保护、证据链                                            |
| 语义         | pytest + 固定 Turtle 夹具      | SHACL 报告结构、OWL 一致性、A08 状态切换                              |
| 前端单测     | Vitest                         | 布局算法、图谱过滤组合（迁移 demo `knowledge-graph.test.cjs` 的断言） |
| 契约         | Schemathesis / OpenAPI diff    | 接口变更可感知                                                        |
| E2E（M3 起） | Playwright                     | 8 步贯通脚本，跑在 seed 后的样例库上                                  |
| i18n         | 自定义脚本                     | zh/en key 差异率 = 0，缺失即失败                                      |
| 许可证       | pip-licenses / license-checker | 禁止 GPL/AGPL                                                         |

demo 的 `tests/*.cjs` 断言（图谱邻域深度与过滤器组合、本体合并后结构完整性、模板来源与命名空间规则）**全部迁移**，作为 M1/M3 的回归基线——这批断言已经踩过坑，价值很高。

---

## 9. Definition of Done

**v0.1.0（M3）**：

1. P0 共 22 项全部上线，无占位按钮，无"只弹提示不干活"的控件；
2. 9 个主流程环节在真实只读库上连续走通，全程不离开系统界面；
3. M3 贯通测试 8 步一次性全通过；
4. 幂等 / 失败保护 / 结果集切换 / 证据追溯四项有自动化断言；
5. 校验报告未执行项如实标注；
6. 实测规模上限写入 README；
7. 中英双语可切换（界面 + 消息 + 领域标签）；
8. `make up` 单机一体可跑，含 seed 数据。

**v1.0.0（M4）**：追加规范符合性（M-01~M-07）、导入导出闭环、A08 真实执行、i18n 100% 覆盖、社区基建齐备。

---

## 10. 风险清单

| #   | 风险                      | 影响                               | 应对                                                             |
| --- | ------------------------- | ---------------------------------- | ---------------------------------------------------------------- |
| 1   | H-04 语义引擎接入延期     | 卡住 H-50/H-32/M-01                | M0 内完成 PoC 并锁定组件，不通过不进 M1；语义层做成可替换适配器  |
| 2   | H-03 IRI 治理被当小功能   | 更名重算牵动四处，事后补必返工     | 与 H-11 同期交付，影响面扫描做成独立接口                         |
| 3   | i18n 只做界面不做领域内容 | 英文版"中文内核"，项目无法真正对外 | L3 双语字段在 M1 随资源模型落地，英文缺失时 UI 标注"未翻译"      |
| 4   | 标准文本版权              | 开源项目合规事故                   | 只存条款编号 + 自撰描述，不抄正文，PDF 不入库；CONTRIBUTING 明写 |
| 5   | 版本冻结语义被简化        | 可审计性崩塌                       | 冻结逻辑列为独立验收项 + 集成测试                                |
| 6   | 关系属性塞进三元组        | 证据丢失                           | 关联实体模式 M1 落地，M3 验收含"两条参与记录分别保存"            |
| 7   | 未执行被当通过            | 合规风险                           | 四态在 H-50/H-51 硬编码，A08 未接入前强制"未执行"                |
| 8   | 样例库质量不足            | M2/M3 验收变空话                   | 样例库为 M2 正式交付物，必须含三类结构 + 重复参与记录            |
| 9   | 一人维护 47 项功能        | 项目烂尾                           | 严格划 P0=22 项；M3 即对外发布，用社区反馈决定 M5 顺序           |

---

## 12. 工程规范（已落地，M0 前置）

已在本仓库生效，配置即真值源：

| 保障           | 工具                                                                                     | 配置位置                               |
| -------------- | ---------------------------------------------------------------------------------------- | -------------------------------------- |
| 前端语法与风格 | ESLint 9（flat config）+ `@intlify/vue-i18n`（**禁止模板裸文本**）+ `simple-import-sort` | 根 `eslint.config.js`                  |
| 前端类型       | vue-tsc（strict、noUnusedLocals、verbatimModuleSyntax）                                  | `web/tsconfig.app.json`                |
| 统一格式化     | Prettier（行宽 100、单引号、无分号）                                                     | `.prettierrc.json` / `.prettierignore` |
| 后端语法与风格 | Ruff（lint + format，替代 black/isort/flake8）                                           | `server/pyproject.toml` `[tool.ruff]`  |
| 后端类型       | Mypy（`disallow_untyped_defs`，函数签名必须有注解）                                      | 同上 `[tool.mypy]`                     |
| 提交规范       | commitizen + cz-git（`npm run commit`）+ commitlint 强校验                               | `commitlint.config.cjs`                |
| 提交前钩子     | husky + lint-staged（改什么校验什么）                                                    | `.husky/` + `package.json`             |
| CI             | GitHub Actions：ESLint / Prettier / vue-tsc / Ruff / Mypy / Pytest                       | `.github/workflows/lint.yml`           |
| 编辑器一致性   | EditorConfig（LF、UTF-8、末尾空行）                                                      | `.editorconfig`                        |

一键入口：`make lint`（全量）、`make fix`（自动修复）、`make test`（后端测试）。详见 `CONTRIBUTING.md`。
**不入库**：`demo/`、`.workbuddy/`、`node_modules/`、`.venv/` 已在 `.gitignore` 排除（`git check-ignore` 已验证）。

---

## 11. 待拍板（4 项，确认后即可开工）

1. **UI 框架**：推荐 **Naive UI**（表格一体化 + TS 类型 + 运行时主题）；若更看重社区规模与组件齐全度，次选 **Element Plus**。建议 M0 用"实体实例列表"真实页面验证两天再定稿。
2. **项目显示名**：仓库已定为 `Loinver/knowledge`，对外产品名建议 `SemanticForge` / `KnowledgeHub` / `OntoFlow`（影响包名、文档标题、域名）。
3. **后端确认**：是否接受"Python FastAPI + rdflib/pySHACL，OWL-DL 走可选 Jena sidecar"。若目标场景必须出具标准符合结论，可改 Java + Jena 主栈，代价是迭代速度。
4. **开工范围**：先交付 M0 可运行骨架（迁移 + 语义 PoC + i18n 骨架 + 一个真实列表页），还是一次性把 M0+M1 的目录骨架与接口契约铺完再填实现？
