# 知识中台完整性缺口修复验收记录

执行日期：2026-09-26（Asia/Shanghai）
执行基线：工作区（报告基线 commit `5a5e0d3` + 未提交的命名空间修复）
对应缺口清单：[docs/kg-platform-completeness-report.zh-CN.md](./kg-platform-completeness-report.zh-CN.md)

本记录对照完整性核验报告的第 9 节修复分批，逐项说明本轮实际落地的内容、自动化与浏览器实测证据，以及如实保留的遗留事项。未在本轮范围的项目保持报告原结论，不做改写。

## 1. 执行摘要

按批准的计划执行了报告的第一批（打通闭环）与第二批（P0 图谱形态与推荐）以及 12 步界面级 E2E 核验。结果：

| 核验项           | 结果                                                                    |
| ---------------- | ----------------------------------------------------------------------- |
| `make lint`      | 通过（ESLint / vue-tsc / Prettier / Ruff / Mypy / 架构边界 116 项）     |
| `make test`      | 通过：前端 node --test 77/77，后端 pytest 656/656                       |
| `make test-e2e`  | 通过：`e2e/m3-browser-flow.spec.ts` 单套件含新增第二批验收段，1 passed  |
| i18n             | `check-i18n-keys.mjs` 通过，zh-CN / en-US 各 1068 键                    |
| 许可扫描         | Web 85 包通过；Python 扫描通过（含两项新增 allow-only 决策，见第 5 节） |
| 五场景浏览器实测 | 10 张截图核验通过（`docs/assets/kg-accept-*.png`），见第 4 节           |

五场景装配结果（隔离库，`scripts/seed_five_scenarios.py` 驱动真实 API 全流程）：73 实体、46 条直接事实、**18 条派生边**、43 条隔离记录（含规则命中 12 份缺签约方合同与 1 组持股合计超限证据行），运行状态如实为 PARTIAL。

## 2. 第一批：闭环打通（对应报告断点 1–7 与 P0-02/03/04/07/08）

| 报告缺口                               | 本轮落地                                                                                                                                                                 | 关键文件与测试                                                                                   |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| 断点1/P0-01 命名空间入口               | 工作区既有修复（管理页 + 就地登记 + 后端校验/删除保护）；本轮补 API 层 409 测试与 e2e 路由冒烟，并在五场景/e2e 中全程界面验证                                            | `server/tests/test_api_envelope.py`、`e2e/m3-browser-flow.spec.ts`                               |
| P1-03 五场景正式样例                   | `samples/seed.sql` 扩展为 17 表（部门自引用四层两树一孤儿、PERSON/ENTERPRISE 多态股东、双角色客商、合同签约方/补充协议），`enterprise_demo.sqlite` 重建                  | `samples/seed.sql`、`samples/README.md`                                                          |
| P0-08 多态端点 + 业务键融合            | 端点规范支持 `candidates`（列非空/判别字段 `type_field`/二跳经由 `via`）；实体映射支持 `match_keys` 跨表业务键融合（同键同 IRI、双来源证据保留）                         | `schemas/mapping.py`、`mapping_service.py`、`extraction_service.py`；`test_m3_mapping_fusion.py` |
| P0-04 边属性载荷                       | `GraphTriple.props` / `DerivedEdge.props`；ASSOCIATIVE 属性随边落库；graph-view 边输出与前端边标签/事实表展示                                                            | `models/extraction.py`、迁移 0013；`test_m3_mapping_fusion.py`                                   |
| P0-03 抽取阶段3规则校验                | 显式阶段3：实例校验报告（I01–I06）+ 本体钉扎的 AUTO DATA 规则（无环/合计上限/唯一键/必备端点/日期格式），命中写隔离并计数；SHACL/OWL 如实 NOT_RUN                        | `extraction_rule_stage.py`；`test_m3_rule_derivation_stages.py`                                  |
| P0-03/V-RU-05 抽取阶段4派生边          | `Rule.language=DERIVATION`（transitive / symmetric / co_occurrence / product_chain），产出 `DerivedEdge(rule_id, source_fact_ids, props)`，`derived_edge_count` 真实计数 | `derivation_service.py`、迁移 0013；`test_m3_rule_derivation_stages.py`                          |
| P0-02 资产校验 A05/A06 恒 NA           | A05 真实核对钉扎规则（缺失/漂移/表达式可解析）；A06 核对模板成员是否被本体保留；无规则/非模板装配时如实 NA                                                               | `validation_service.py`；`test_m4_graph_analysis.py`                                             |
| P0-07/V-TR-03/05 证据冻结链 + 反向追溯 | `FactEvidence` 增加 mapping/ontology/resource/rule 四类冻结引用（迁移 0013）；新增 `GET /extraction/evidence/trace/reverse`（源行→事实→实体）                            | `evidence_service.py`；`test_m4_graph_analysis.py`                                               |

## 3. 第二批：P0 图谱形态、推荐与模板（对应 P0-05/06）

**布局注册表**：`web/src/views/graph/components/layouts/index.ts`——每形态一个纯函数插件（可 node --test 直测），形态 id 与后端推荐一一对应；`GraphBrowse` 形态选择器写入 route query（保持 center/graph/过滤上下文）。引入 `d3-hierarchy`、`d3-force`（ISC/MIT，避开 d3-delaunay 的 Unlicense 依赖，许可扫描通过）。

| 形态              | 说明                                                                | 验收截图                                                |
| ----------------- | ------------------------------------------------------------------- | ------------------------------------------------------- |
| G-01 组织架构树   | 自引用边折线树，父子分层；环结构退化为网格（环检测由规则阶段承担）  | ![组织架构树](./assets/kg-accept-02-org-tree.png)       |
| G-06 股权穿透图   | 按持股方向分层（股东在上、被投企业在下），比例在边上（props）       | ![股权穿透图](./assets/kg-accept-03-equity.png)         |
| G-07 实际控制人链 | 优先用派生乘积边（间接持股）分层成链                                | （与股权穿透同族，控件内切换）                          |
| G-10 力导向网络   | d3-force 确定性模拟（固定初值/迭代，可复现），直接/派生线型图例     | ![力导向网络](./assets/kg-accept-06-force.png)          |
| G-11 自我中心环   | 原有 1/2 度距离环，中心高亮                                         | （原有能力，回归通过）                                  |
| G-16 本体模式图   | 类型级聚合视图，节点显示类型与实例计数，点击下钻                    | ![本体模式图](./assets/kg-accept-07-schema.png)         |
| G-17 客商供应链图 | 买卖两端分列、双角色节点居中，金额在边上                            | ![客商供应链图](./assets/kg-accept-04-supply-chain.png) |
| G-21 时间轴       | 按类型分泳道，横轴按首个日期属性，无日期节点排尾部                  | ![时间轴](./assets/kg-accept-05-timeline.png)           |
| G-24 版本差异     | `GET /extraction/graph/{a}/diff/{b}` 集合差 + 抽屉展示实体/事实增删 | （抽屉在 e2e 中断言）                                   |
| G-12 关系路径     | `GET /extraction/graph/{id}/path` 有向 BFS + 抽屉结果与画布高亮     | （抽屉在 e2e 中断言）                                   |
| G-26 证据溯源链   | 证据表"查看链"→ 事实→来源行→运行→四类冻结版本链卡                   | ![证据溯源链](./assets/kg-accept-10-evidence-chain.png) |
| G-28 质量叠加     | 隔离命中节点红标 + 图例（截图：12 份缺签约方合同全部命中）          | ![质量叠加](./assets/kg-accept-08-quality-overlay.png)  |
| G-30 实体 360     | 实体详情页分区跳转各形态 + 证据链入口                               | （详情页控件在 e2e 路由冒烟内）                         |
| G-02/G-09         | 缩进目录树随树族实现；环路以规则阶段 + 布局环安全承担               |                                                         |

**形态推荐**：`graph_recommendation_service.py` 从冻结本体快照提取结构语义信号（自引用/传递/对称/带度量关联/日期属性/乘积派生规则），输出形态 + i18n 理由参数；**改名不变性**有专项测试（IRI/名称不同、结构相同 → 相同推荐）。**视图模板**：`ViewTemplate` 模型 + CRUD + 本体版本失效（stale）提示（迁移 0014），前端保存/应用/失效标签。通用能力：PNG/SVG/CSV 导出、图例、截断/空态、双语、键盘可达（e2e 断言）。

## 4. 五场景浏览器实测

环境：隔离元数据库 + `samples/enterprise_demo.sqlite`（五场景版），uvicorn :8010 托管构建产物；登录、导航与操作均为界面路径（环境准备使用脚本装配数据，未预触发被测功能）。截图存于 `docs/assets/kg-accept-*.png`：

1. 总览类型网格：73 节点/64 边、隔离警告 43 条如实展示、推荐条与全部控件（![总览](./assets/kg-accept-01-overview.png)）
2. 组织架构树（以总部为中心的子树）
3. 股权穿透（持股分层 + 比例边；含刻意保留的 1002↔1007 环，布局环安全）
4. 客商供应链（两端分列 + 金额边）
5. 时间轴（合同/项目泳道 + 日期横轴）
6. 力导向网络（图例、直接/派生线型）
7. 本体模式图（类型计数：Contract 16、Department 6、Partner 3……）
8. 质量叠加（12 份缺签约方合同红标 = 规则命中数一致）
9. 反向追溯：`eq_equity_holding#3001` → 1 条事实 → Person/8001 与 Enterprise/1001 双实体链接（![反向追溯](./assets/kg-accept-09-reverse-trace.png)）
10. 证据链：事实 → 来源行 → 运行批次 → 冻结版本（隔离命中行标"存在隔离问题"）

实测中发现并修复一个真实缺陷：**分层布局在环数据上死循环**（股权穿透页卡死渲染进程）——`assignLevels` 增加层级上限（节点数）后修复，回归测试与全部截图通过。该缺陷正是五场景样例中刻意保留的持股环暴露的，属于本轮验收的有效产出。

测试环境说明：ZCode 内置浏览器对本页的截图能力持续超时（运行时限制，已如实记录），视觉证据改用仓库 Playwright 无头 Chromium 对同一构建产物截图，并经人工查验；交互与 DOM 断言由 e2e 套件覆盖。

## 5. 许可与配置决策

- `cryptography 48.0.1`（`Apache-2.0 OR BSD-3-Clause`）与 `cffi 2.1.1`（`MIT-0`）加入 `scripts/check-python-licenses.sh` allow-only：两者均为宽松许可族（Apache-2.0/BSD/MIT 族内），与 `security-and-license.md` 白名单不冲突；cryptography 维持 `<50` 钉扎（50.x 无 macOS + py3.13 wheel，见 `.agents/AGENTS.md` 已知坑）。
- Playwright e2e 端口改为隔离的 API :8123 / 前端 :5199（`playwright.config.ts` + `web/vite.config.ts` 的 `KG_API_PROXY_TARGET`），修复报告 P1-06 的端口占用环境阻断。
- Alembic 迁移 0013/0014 已在 `server/knowledge.db`（开发库）实际执行：仅可空列新增与 `view_template` 新表，执行后 30 个建模资源完好、`PRAGMA integrity_check` 通过。旧库升级命令：`cd server && .venv/bin/alembic upgrade head`。

## 6. 如实保留的遗留事项（未在本轮范围）

- **第三批**：P1/P2 增强形态（旭日图、弦图、桑基、邻接矩阵、地理分布、社区聚类、小多图等约 15 个）、抽取异步任务/取消/调度/增量（V-EX-06）、设计器画布直接建模（V-DS-03）、权限矩阵逐路由验收（P1-05）、1 万实体/5 万事实规模压测（P2-03/04）。
- **AI 功能**：V-DS-05 设计器 AI 补全、V-EX-07 文档抽取/AI 映射——按报告口径保持"待产品决策"，本轮未实现。
- **A08**：完整 OWL-DL 推理器仍未接入，资产校验 A08 保持 NOT_RUN（合规底线：未执行绝不显示通过）。
- **SECURITY.md 缺失**（报告 P1-08）：该删除先于本轮存在、非本轮产物，仍待原改动负责人处理；`.agents/conventions/security-and-license.md` 的漏洞报告入口继续失效。
- e2e 主流程仍通过 API 预置本体与映射后从界面继续（报告 6.1 口径）；第二批新增的命名空间登记与规则创建已做到全程界面，完整 12 步"零 API"spec 列为后续工作。
- 未提交改动：本轮全部改动留在工作区，请按 `pnpm run commit`（git-cz）分组提交；`git status` 已确认不含 demo/、.venv/、dist/、node_modules/。

## 7. 第三批与 AI 功能（2026-09-27 追加执行）

| 项目                                       | 落地                                                                                                                                                                                                                                                                                               | 证据                                                                                                           |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| A08 OWL 一致性（报告第三批第 1 条）        | owlrl OWL 2 RL 闭包真实执行：矛盾经 `error_messages` 原样进四态（草稿本体 NA、未发布/引擎缺失 NOT_RUN）；DL 完整推理仍超出范围并在 message 中如实标注                                                                                                                                              | `app/semantics/rdflib_backend.py`、`tests/test_semantics_consistency.py`、`test_m1_validation.py`              |
| 异步抽取任务（V-EX-06 / P1-04）            | `extraction_task` 表（迁移 0015）+ 调度线程 + 协作取消 + 阶段进度 + 增量水位（实体映射可配 `incremental_field`，按上次成功任务水位过滤并写出新水位）                                                                                                                                               | `extraction_task_service.py`、`tests/test_m5_extraction_tasks.py`（5 项含增量/调度/取消）                      |
| 权限矩阵（P1-05）                          | 匿名/VIEWER/EDITOR/ADMIN × 23 条路由全矩阵断言（401/403 判据），另补 VIEWER 写保护与 EDITOR 管理路由两条专项                                                                                                                                                                                       | `tests/test_permissions_matrix.py`                                                                             |
| AI 建议（V-DS-05 / V-EX-07，产品决策落地） | OpenAI 兼容客户端只走显式环境配置（`KG_LLM_BASE_URL/KEY/MODEL`），未配置如实 `KG.LLM_NOT_CONFIGURED`；三类建议（本体补全/映射建议/文档抽取）每条带解释与结构化内容，人工逐条应用/忽略；应用只写草稿资产（已发布资源/映射拒绝）；设计器、映射向导、AI 助手页（`/extraction/ai-assist`）接入审阅面板 | `app/core/llm.py`、`app/domain/ai_suggestion_service.py`、迁移 0016、`tests/test_m5_ai_suggestions.py`（7 项） |
| 增强形态（P1/P2）                          | 新增 9 布局：集团族谱、环路检测（环上实体内环）、二部图、社区聚类（连通分量分块）、多方关系（枢纽内环）、类型流向桑基、类型圆周弦图、地理分布（按区域属性聚块，无区域节点收尾块不丢弃）、影响面（被依赖者在上的反向树）；另有邻接矩阵与中心性排行抽屉、时间轴日期回放滑块                          | `layouts/index.ts`、`GraphBrowse.vue`、布局测试 82/82                                                          |
| 规模压测（P2-03）                          | `scripts/benchmark_scale.py` 实测：1 万企业源 + 5 万任职行 → 抽取成功产出 6 万实体（含 5 万 stub）/ 5 万事实，耗时 299 秒（SQLite+逐行证据写入为主瓶颈）；图谱视图全图查询 0.08 秒；结果存 `/tmp/kg-benchmark/result.json`                                                                         | `scripts/benchmark_scale.py`                                                                                   |
| 主 chunk 拆包（P2-04 部分）                | Vite `manualChunks`：业务主 chunk 700 kB → 121 kB；naive-ui（792 kB，可缓存）与 vue/d3 各自成块                                                                                                                                                                                                    | `web/vite.config.ts` 构建产物                                                                                  |

划分图补充（2026-09-27 第二轮）：G-03 旭日图、G-04 矩形树图、G-05 圆形打包图已实现——布局层新增 marks 标记通道（扇形/矩形/圆，d3-hierarchy partition/treemap/pack 真实布局），画布按标记渲染，层级为"本体 → 类型 → 实例"（面积按实例计数），实例点击下钻、类型色图例、双语；形态选择器与推荐通用列表同步。实测截图：![旭日图](./assets/kg-accept-11-sunburst.png)、![矩形树图](./assets/kg-accept-12-treemap.png)、![圆形打包图](./assets/kg-accept-13-pack.png)。

诚实说明：G-22 甘特需要区间条渲染、G-29 融合解释图与 G-31 小多图未实现——均保持未实现结论，不以近似实现冒充。许可 allow-only 追加 `cryptography`（Apache-2.0 OR BSD-3-Clause）与 `cffi`（MIT-0），均在白名单许可族内。

## 8. 结论

报告第一批与第二批的全部 P0 闭环缺口已实现并通过自动化与五场景浏览器实测；"从实体类型一路走到五类场景图谱和证据追溯"的主流程可以在不改代码、不手工改库的前提下于界面内完成。遗留事项即第 6 节所列，与报告第三批口径一致。
