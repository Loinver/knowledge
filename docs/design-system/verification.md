# 验证与实际执行记录

本记录只描述本任务实际执行的结果。测试启动与历史结果不算通过。

## 基线与当前范围

- 2026-11-23：初始工作区干净，HEAD `13b5a3a`。源码、项目规则、运行入口和消费者盘点已完成。
- A/B/C1/C2/C3 已完成定向功能验收。C4 页面已迁移，独立复核发现的查询隔离和草稿问题已修复并通过独立复核。Naive 运行时、Provider、主题和构建分包已删除；当前授权前端范围已完成验收，最新结果见末节；历史阶段结果保留原范围。
- 提交协调期间曾停止写入。提交聊天中断后，用户明确批准“解除停写，继续迁移”；当前继续保留全部工作区改动，不代为提交。
- 下列日志在本机 `/private/tmp`，属于可检查的本地证据，不表示 CI 或最终提交树通过。

## B 批次已有证据

以下历史日志已于续接时重新读取最终结果；后续 C1 改动不自动继承这些结论。

| 检查             | 实际结果与范围                                                | 证据                                                |
| ---------------- | ------------------------------------------------------------- | --------------------------------------------------- |
| 真实业务试点     | 5/5；实体表单、知识库失败草稿、远程分页、嵌套命名空间、VIEWER | `/private/tmp/knowledge-ui-pilot-b-final.log`       |
| 共享组件         | 40/40                                                         | `/private/tmp/knowledge-ui-components-b.log`        |
| 应用构建         | 成功；存在 chunk 大小提示，尚未完成旧 Naive 分包删除          | `/private/tmp/knowledge-ui-build-b.log`             |
| 前端完整依赖许可 | 生产与开发 192 项通过；精确许可例外见 dependencies.md         | `/private/tmp/knowledge-ui-licenses-all-b.log`      |
| 独立增量复核     | Boyle，范围限 B 修复增量；20 个真实浏览器场景                 | `/private/tmp/knowledge-ui-review-b-incremental.md` |

构建耗时和产物大小只代表该次本机执行，不作性能改善结论。

## C1 续接验证

2026-11-23，基于当前工作区执行：

- 定向 Node 回归 **122/122**：`selection-lifecycle`、`semantic-fields`、`governance-render`、命名空间、关系类型、配置、业务域及共享表单/控件/表格测试。退出码 0；无跳过。
  日志：`/private/tmp/knowledge-ui-c1-resume-tests.log`。
- 属性编辑器先检查权限/冻结/忙碌，再更新会话身份。新增可观察的草稿回归：被拒绝的打开操作不能重置旧草稿的关闭保护。
  `node --test src/__tests__/governance-drafts.test.mjs`：**7/7**，退出码 0；日志 `/private/tmp/knowledge-ui-c1-draft-guard.log`。
- `pnpm exec playwright test e2e/relation-edit-lifecycle.spec.ts`：**2/2**，退出码 0。覆盖保存中关闭仍完整保存原资源、旧读取不覆盖新草稿，核对真实 HTTP 写入对象和 edit_revision。
  日志：`/private/tmp/knowledge-ui-c1-relations-browser.log`。
- `pnpm -C web typecheck`、C1 目标 ESLint、两处新增修改的 Prettier、`git diff --check` 通过。
  日志：`/private/tmp/knowledge-ui-c1-types.log`、`/private/tmp/knowledge-ui-c1-eslint.log`。这些结果早于后续属性字段校验补全，补全后须重跑相关检查。
- i18n：两份语言包 2147 个 key 一致，后续新增字段校验文案后重新检查。
- C1 五类列表与试点浏览器首次 **23 passed / 2 failed**；两失败为本体/命名空间空态文字定位。`UiEmpty` 增加独立说明节点，表格自定义空态取消重复 padding；受影响的 empty/503 四场景重跑 **4/4**。503 不同时显示空库文案。证据：`/private/tmp/knowledge-ui-c1-browser-states.log`、`/private/tmp/knowledge-ui-c1-empty-retry.log`。试点的 Select 无效态在选择合法值后清除，已在前一组 23 项中验证。
- 本体/命名空间卸载后不处理旧 publish/remove 的 success/error/finally；本体编辑使用最新详情标签及相应 revision。相关 audit、namespace、table Node **46/46**，日志 `/private/tmp/knowledge-ui-c1-followup-tests.log`；目标 ESLint 通过。该 lint 配置忽略 e2e TS，不将 ignored warning 当成已检查。
- Averroes 独立复核提出两项 P2：关系成对基数的兄弟字段错误未重校，字典缺少动态 Field 路径及错误焦点。报告 `/private/tmp/knowledge-ui-c1-quality-review.md`；首轮结论为 `CHANGES_REQUIRED`，没有 P1。另确认关系端点 required 文案不能随已打开表单切换语言，已纳入修复。
- 关系规则现捕获两端具体值以联动重校，端点规则响应 locale。修复后的 Node **17/17**；编辑基数浏览器 **1/1**，证明无效值零 PUT、只修正 max 后两字段清错、有效值恰好一次 PUT。证据：`/private/tmp/knowledge-ui-c1-relation-unit-retry.log`、`/private/tmp/knowledge-ui-c1-cardinality-browser.log`。原两项编辑生命周期场景在同轮另一进程仍为 **2/2**；首次新场景因隔离登录夹具超时未进入业务操作，不能算产品通过。
- 正在补充：关系新建两端基数/首错焦点，字典动态行/失败保留，属性高精度边界及基数，模板字段与共享搜索消费，以及独立增量复核。关系新建首次在 signedIn 的 API 等待夹具超时，尚未进入目标业务断言；当前后续结果未取得前不记为通过。

### C1 字段反馈后续结果

- 关系新建与编辑分离校验锁和网络提交状态，保留重复提交及旧会话归属；接入 SearchPanel/SearchTable（local），查询/筛选空态和计数未知态明确。当前关系定向 Node **21/21**：`/private/tmp/knowledge-ui-c1-relation-current.log`。真实新建两端分别改 min/max，均清除成对错误且首错获得焦点，合法仅一次 POST：**1/1**，`/private/tmp/knowledge-ui-c1-relation-create-browser.log`。目标 ESLint 通过。
- Averroes 对关系当前增量独立结论 **PASS**，18 项目标测试与23项独立检查通过；覆盖两种表单×两端×两种修正、已打开表单双语错误、旧校验 finally、重复提交、卸载后 publish/remove。报告 `/private/tmp/knowledge-ui-c1-relations-increment-review.md`。此 PASS 不覆盖字典、属性或全站。
- Lagrange 属性实现与相邻回归 **31/31**（其中新增属性12项）：`/private/tmp/c1-property-regression.log`。属性真实浏览器断言已通过：先进入数据属性页签，空表单聚焦、跨字段清错、无效零写、合法一次写、API保存原始高精度十进制字符串；证据 `/private/tmp/knowledge-ui-c1-fields-browser.log` 中的 property 场景。
- 上一日志合计1 passed/1 failed，失败来自字典测试把失败注入错误配置到 `/enum-dictionaries`，未命中真实 `/governance/enum-dictionaries`。已修正夹具并重跑字典，尚未取得最终结果时不称通过。
- 隔离登录等待间歇超时的最小 API 诊断没有复现超时：直连分别136/41/22ms，代理522/528ms；第六次失败登录触发真实429，耗时2476ms，诊断的“恒为401”假设不成立。该探针只在新隔离库运行，既不是业务测试通过也不能确定此前超时根因。未增加产品/测试默认超时；后续正常属性业务回归按原阈值通过。
- 文档执行者 Fermat 已按实际源码补齐共享组件类型、props/emits/slots、双语用法和消费者，89个本地链接、47个组件引用、3个Vue示例语法及Prettier通过；无消费者或仅声明能力仍明确列为待清理/落实。Chief修正知识库 TableToolbar 的 title 调用为真实 label prop。
- 当前两份locale **2160 keys** 一致。属性及模板/字典后续审查、当前整合类型检查仍待完成。

浏览器测试首次因沙箱禁止绑定 8123 而未能启动；随后通过审批使用项目规定的本机隔离服务重新执行。测试使用新临时数据库，无开发库读写；同数据前后截图的专用临时库未用于这些失败/CRUD 测试。

### C1 收尾补证（2026-11-23）

- 字典 D1：删除无关前置行后，重复值错误按新路径保留；再删除一个重复参与者后清错。实际表单 Node **8/8**，日志 `/private/tmp/knowledge-ui-c1-dictionary-remap-tests.log`；真实浏览器三行场景通过，另验证 503 后保留草稿。Averroes 独立增量 **PASS**，报告 `/private/tmp/knowledge-ui-c1-dictionary-incremental.md`。报告明确披露额外合成实例替换实验不成立，未将整个 probe 退出 1 宣称通过。
- 属性 URI：Halley 修复既有 anyURI 默认值的词法校验；Boyle 对56例前后端差分独立 **PASS**。真实浏览器非法三值零 PUT、首错焦点，以及合法相对 Unicode URI 原文保存通过。证据：`/private/tmp/knowledge-ui-c1-property-uri-incremental.md`、`/private/tmp/knowledge-ui-c1-completion-browser.log`。后者总计3通过/1登录夹具失败，仅采信其中实例化、字典和 URI 通过场景。
- 模板：metadata、资源 pin、从本体与实例化字段接入真实 Form/Field，保留各模式 payload 与会话身份；搜索表格使用真实远程 total。首轮22项中20通过、2项测试夹具断言失败；修正后4项定向复跑全部通过，未更改产品来迎合错误断言。日志 `/private/tmp/knowledge-ui-c1-template-targeted.log`，实施报告 `/private/tmp/knowledge-ui-c1-template-implementation.md`。
- 模板 metadata 真实浏览器 **1/1**：无效零 POST、首错焦点、503保留草稿、重试成功后通过 GET 核对对象名称/revision/空资源集合，保存后继续编辑。该流程与原源码一致；旧测试错误要求关闭弹窗，已修正为真实业务验收。日志 `/private/tmp/knowledge-ui-c1-template-metadata-final.log`，进程退出0。模板实例化浏览器已验证原模板 If-Match 及合法一次写。
- 当前 C1 目标 ESLint、整合 `vue-tsc --noEmit -p tsconfig.app.json` 均退出0；两份语言包 **2167 keys** 一致。日志 `/private/tmp/knowledge-ui-c1-final-eslint.log`、`/private/tmp/knowledge-ui-c1-final-types.log`。随后计数展示补充 Intl 与加载/错误未知态，另做定向 lint/SSR 检查。
- 迁移清单重新生成：86个初始文件，66个仍含旧体系引用（包含测试与CSS）；41个路由页面。此数字只表示源码盘点，不表示66个运行时页面，也不代表全站验收。
- Boyle 模板独立 Quality **PASS**，最新计数展示版本已包含；22例实际 helper 与后端 schema 差分完全一致，报告 `/private/tmp/knowledge-ui-c1-template-review.md`。
- 词典重置现在同时恢复查询、名称升序和第1页；清空只清查询并保留排序。定向真实页面 handler **4/4**，`/private/tmp/knowledge-ui-c1-dictionary-reset-tests.log`；目标 lint 通过。
- 新增 `e2e/design-system-c1-search.spec.ts`：各21条隔离真实记录验证服务端第2页、加载反馈、503重试、草稿查询不请求、Enter单请求、无匹配和重置。字典与修正后的模板场景均通过；模板空库旧测试文案更新后也通过。日志 `/private/tmp/knowledge-ui-c1-search-browser.log`（2通过/1真实计数展示失败）与 `/private/tmp/knowledge-ui-c1-template-search-final.log`（修复后1/1）。
- 上述失败发现共享表格首次加载错误显示0项。UiDataTable 现在在加载/错误/尚未查询时将工具栏和页脚 total 标为 undefined，分页隐藏数量且保留请求页码；成功0仍显示0。实际共享表格 **20/20**，`/private/tmp/knowledge-ui-c1-count-table-tests.log`；目标 lint/format 与整合类型检查退出0（`/private/tmp/knowledge-ui-c1-count-types.log`）。实体试点补传 loading，知识库自定义工具栏改消费 slot total。
- `ui-redesign-states` 配置页8场首次为5通过/3失败：两场在无关治理规则夹具 POST 时超时，未进入字典页面；另一场模板旧空态文案已修并补验。前两场对应业务由上述最小夹具覆盖，但不宣称这份8场日志全绿。首请求间歇超时诊断为 **INCONCLUSIVE**：`/private/tmp/knowledge-ui-c1-e2e-startup-review.md`。没有提高 timeout 或增加重试掩盖。

## C2 数据集成定向验证（通过）

- 数据源接入真实 Form/Field、SearchPanel/SearchTable local，新增 create/edit 会话与输入版本归属，空凭据省略且密码原文保留。定向 Node **15/15**；独立 Averroes 复核 **PASS**，复跑15项和补充4项竞态。证据：`/private/tmp/knowledge-ui-c2-sources.md`、`/private/tmp/knowledge-ui-c2-sources-tests.log`、`/private/tmp/knowledge-ui-c2-sources-review.md`。
- 数据源真实浏览器场景通过：无效零写、首错焦点、503保留输入、拒绝关闭脏草稿、重复提交、真实新建/编辑、空凭据请求省略、21条本地分页、搜索 Enter/重置各一次。检查1440×900、1280×720、768×1024、390×844，截图元数据包含DPR/缩放。证据：`e2e/design-system-c2-forms.spec.ts` 与 `/private/tmp/knowledge-ui-c2-forms-fusion-browser.log` 首项；该轮另外两项失败，不称整轮通过。
- 任务接入真实校验、日期与布尔字段及写会话保护；无 total 接口采用 mode=none 与真实前后页，保留轮询/卸载/权限。私有 Node **13/13**，证据 `/private/tmp/knowledge-ui-c2-tasks-final-tests.log`；首错焦点和固定页脚修复后，真实浏览器任务创建通过；日期/false/pin/失败留稿/重复提交均核对。新增权限变化、Select change 的定向 Node 13/13；独立 Averroes 原缺陷5/5与旧finally新锁4/4通过，T1/T2关闭。
- 运行和隔离记录定向 Node **12/12**；实际成功运行摘要/冻结清单/kbReturn/隔离导出、无 total 满页后空页可返回、真实 FAILED 保留当前结果集与非空隔离导出分别通过。三份日志 `/private/tmp/knowledge-ui-c2-runs-browser.log`、`knowledge-ui-c2-runs-browser-final.log`、`knowledge-ui-c2-runs-failure-final.log` 前两轮各含一个后续已修的夹具/断言失败。启动API返回当前图谱，失败时返回此前成功图谱是现有契约，最终核对其旧id/run_id而非错误要求null。Boyle 对运行与共享计数差异独立 **PASS**，报告 `/private/tmp/knowledge-ui-c2-runs-review.md`。
- 任务/AI公共回归 **12/12**；适配测试SFC加载器解析Reka外部类型与无script组件。证据 `/private/tmp/knowledge-ui-c2-common-tests-final.log`。数据集成目标ESLint和整合vue-tsc退出0，分别在 `/private/tmp/knowledge-ui-c2-eslint-final.log`、`knowledge-ui-c2-types-final.log`；后续增量仍需补查。i18n **2170 keys** 一致。
- 目录/预览/AI浏览器首轮6项中 **4通过/2失败**：目录metadata加载/503恢复、空来源、样本空来源、合法零行通过。AI旧测试精确名称未计入必填说明，预览仅错误码缺失败说明，两处修正后的重跑均通过。最新 `/private/tmp/knowledge-ui-c2-browser-retry.log` 共 **7通过/1失败**：另含任务列表加载/503恢复/空态/VIEWER和完整融合；唯一失败为任务创建首次点击。目录私有 Node **37/37**；独立 Lagrange 发现样本小数被默认 Intl 舍入，恢复原值精度后作者37/37、独立双语精度2/2通过，P2已关闭。
- 映射私有 Node **51/51**。完整融合浏览器真实新建→融合配置→预览→发布→SUCCESS→冻结证据→390px→复制草稿→冲突策略→PARTIAL隔离通过；AI来源定位/转义/焦点/保留用户编辑/切换来源使旧建议失效通过。证据 `/private/tmp/knowledge-ui-c2-browser-retry.log`。Boyle 独立复核仅发现空实体集合首错无可聚焦控件；Chief已把添加按钮放入注册字段，Boyle增量独立PASS，M01关闭。
- 任务首次点击诊断确认：pointerdown 时创建按钮 y=732.203，映射 blur 校验插入错误后按钮 y=762.203；同一 clientY=750 的 pointerup/click 命中 form，完整 validate 未被调用。已将操作区移至抽屉稳定 footer 并移除诊断探针；最新2/2浏览器通过（任务创建与映射空集合零写/首错/键盘添加），`/private/tmp/knowledge-ui-c2-forms-acceptance.log`。任务新建抽屉1440×900、1280×720、768×1024、390×844均无横向溢出且操作区在视口内；Chief查看390截图，四档图片及元数据保留于`/private/tmp/knowledge-ui-c2-task-responsive-evidence`。独立 Averroes 的权限代次和Select change两项均已修复通过。证据 `/private/tmp/knowledge-ui-c2-task-click-diagnostic.log`、`knowledge-ui-c2-tasks-review.md`。
- `integration.css`采用语义字号、间距、圆角和统一断点，样本空面板改紧凑高度；清理已无消费者的source-row/filter样式。数据源删除说明按实际引用保护修正，未改变API或删除行为。
- 全部失败/CRUD/分页使用新隔离临时库，未使用before/after截图专用数据。部分测试启动遇到沙箱监听限制或自动审批服务传输失败；命令未执行时不计结果，经正常审批再运行。未提高timeout或增加自动重试。

## C2 完成时的后续范围（历史）

- C2 五域定向验收与独立复核通过。整合vue-tsc、data-integration ESLint退出0，日志`knowledge-ui-c2-types-acceptance.log`、`knowledge-ui-c2-lint-acceptance.log`；M01目标lint/format和E2E TypeScript也退出0。C3按entities/evidence、Designer、路径修复独立范围并行，Chief负责browse/shared/locale/E2E。
- 图谱原有交互修复已有局部证据，控件迁移后须重新逐模式验证；不能以一个 renderer 代替全部模式。
- C2 数据源新建/编辑的旧写响应保护；任务/运行接口没有总数时保留真实的前后页能力，不伪造 remote total。
- 完成全站页面消费后再清理 Naive、Provider、主题适配、旧 CSS、内部选择器、构建分包和临时兼容别名。
- 同数据/同视口/同主题的 after 截图、四种目标视口、双语明暗及实际交互验收。
- 最终 `make lint`、`make test`、build、i18n、API 漂移、许可及必要全站 E2E 尚未执行；当前局部通过不代表全站完成。

## 全站收敛进度（2026-11-23，历史）

以下是该历史阶段的完成结果；后续最终结果见下一节。

| 检查             | 当前结果                                                                                                                                                         | 本机证据                                                       |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| 源码清理         | 86 个初始旧体系文件、0 个运行时残留、41 个路由页；已移除 Naive Provider、主题、legacy CSS、依赖与分包；FormContainer/FormField、rows/mode/selection 使用统一命名 | `migration.json`、`scripts/design-system-inventory.mjs`        |
| 前端单测         | 695/695，0 fail、0 skipped                                                                                                                                       | `/private/tmp/knowledge-final-web-tests3.log`                  |
| 后端单测         | 1757 passed，60 warnings；前次中断不作为通过                                                                                                                     | `/private/tmp/knowledge-final-server-restarted.log`            |
| 完整 lint        | make lint 退出 0，含 ESLint、vue-tsc、全仓 Prettier、Ruff、Mypy 166 文件与架构 175 项                                                                            | `/private/tmp/knowledge-final-lint.log`                        |
| 生产构建         | 退出 0，无 Naive chunk；不把构建时间当性能改善                                                                                                                   | `/private/tmp/knowledge-final-build3.log`                      |
| API 契约         | OpenAPI types are up to date；API、生成类型及服务端没有本任务改动                                                                                                | `/private/tmp/knowledge-final-api.log`                         |
| 双语 key         | 2180 keys，两语言集合一致；包括日期范围辅助技术名称                                                                                                              | `node scripts/check-i18n-keys.mjs`                             |
| web 依赖许可     | production + development 172 项通过，按已批准的精确例外核验                                                                                                      | `/private/tmp/knowledge-final-licenses.log`、`dependencies.md` |
| 共享组件独立复核 | Anscombe：F1–F4 均关闭，限定范围 PASS；异步选项标签、切语言、搜索输入、日期 ID/双语及标题渲染有探针                                                              | `/private/tmp/knowledge-final-shared-review.md`                |
| C4 独立复核      | Volta：R1/R2/R3 关闭；52+23 项回归、9+3 项独立探针通过                                                                                                           | `/private/tmp/knowledge-final-c4-review.md`                    |
| 图谱独立复核     | James：跨层遮挡 P1 关闭，正式组件路径/fit/minimap 24 组检查通过；所有模式的真实点击边界详见报告                                                                  | `/private/tmp/knowledge-final-graph-review.md`                 |

图谱首次完整 31+2 场运行中的两个新增夹具曾把非层级关系要求作为层级显示，随后按正式语义改为同谓词的合法 DAG；反向环仍由通用布局覆盖，不改变层级拒环规则。两场补验通过。最终全站第一批又完整运行 33 个图谱/设计器场景，全部通过，日志 `/private/tmp/knowledge-final-e2e.log`。cycle 当前实际点击通过，旧失败原因未确证，未声称已证明 HMR 是根因。

C4 修正和证据分别见 `c4-query-isolation.md` 与 `c4-knowledge-review-fixes.md`。同查询刷新失败保留成功快照，新查询/页码/筛选/身份立即隔离旧行与 total；文档写动作绑定用户及会话归属；证据关联草稿在撤权和同身份刷新期间保持，禁写与丢弃确认保持有效。

全站浏览器采用项目规定的隔离数据库和受控故障数据，未使用开发库或同数据截图专用库。当前正在校正旧测试的 DOM 定位和必填标签断言；未增加默认超时或重试、未跳过业务断言。最终结果将在本节后续记录。

## 最终验收（2026-11-24）

已迁移41个路由页面，初始86个旧体系文件的运行时残留为0。统一入口为tokens/global/ui CSS，组件采用官方shadcn-vue源码与Reka交互，表格使用TanStack Vue Table，FormContainer/FormField通过VeeValidate验证。Naive依赖、Provider、主题、内部CSS、测试选择器和Vite分包已删除；Pinia、vue-i18n、API客户端、生成类型和SVG/D3保留。

### 已验证

| 检查           | 最终结果及实际覆盖                                                                                                      | 本机证据                                                                                                                 |
| -------------- | ----------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `make test`    | 完整命令前端700/700，后端1757/1757；任务文案后前端再补701/701；0失败/跳过。后端60条既存SQLAlchemy警告保留               | `/private/tmp/knowledge-final-make-test.log`                                                                             |
| lint           | ESLint、vue-tsc、Prettier、Ruff、Mypy166文件、架构175项通过；最后文档再核对格式                                         | `/private/tmp/knowledge-final-lint-terminal.log`                                                                         |
| 生产构建       | 完成，无Naive chunk；不据耗时声称性能改善                                                                               | `/private/tmp/knowledge-final-build9.log`                                                                                |
| 国际化/API     | 2180双语keys一致；OpenAPI types are up to date，API/生成类型/后端源码未修改                                             | `/private/tmp/knowledge-final-api2.log`、`check-i18n-keys.mjs`                                                           |
| 依赖许可       | web生产及开发172条包记录通过，精确许可例外见dependencies.md                                                             | `/private/tmp/knowledge-final-licenses.log`                                                                              |
| 默认浏览器清单 | 当前317个场景全部有实际完成通过记录，清单与Playwright实际catalog逐项匹配                                                | [browser-acceptance.json](./browser-acceptance.json)                                                                     |
| 专项治理       | 5/5：VIEWER只读规则检查、禁写、分区、历史、空态、草稿及模态关闭保护                                                     | `/private/tmp/knowledge-final-governance2.log`                                                                           |
| 专项AI检索     | 1/1完整链：合成模型HTTP协议、真实SQL索引、混合/语义、引文、取消、历史代次和归档引用                                     | `/private/tmp/knowledge-ai-final-retry2.log`                                                                             |
| 专项AI建模     | 2/2：无效输入零生成、生成候选、校验、明确确认、单次草稿应用及VIEWER禁用                                                 | `/private/tmp/knowledge-modeling-final-retry2.log`                                                                       |
| 目录内浏览器   | 9/9由7通过+2修复重跑组成：账户、手机中英明暗工作台、运行清单/失败隔离/未知总量、冻结四态报告                            | `/private/tmp/knowledge-colocated-final-retry.log`、`knowledge-colocated-final-retry2.log`                               |
| 缺译与身份     | 3/3真实场景：映射本体/实体/关系的标签与机读值、export本体/冻结修订、domain新建与编辑英文留空。新Node11/11               | `/private/tmp/knowledge-final-i18n-browser3.log`、`knowledge-final-i18n-labels-unit4.log`                                |
| 图谱           | 24正式模式+2多层关系+7设计器合计33场通过。实体/边选择、普通wheel平移、Ctrl/Meta指针缩放、fit/恢复、每种模式身份分别核对 | `/private/tmp/knowledge-graph-final.log`                                                                                 |
| 图谱相邻链路   | 原生200节点nary、鼠标/浏览器touch协议、导出SVG/PNG、长文及检查器；中断期间的2项超时定向重跑2/2                          | `/private/tmp/knowledge-graph-final.log`、`knowledge-graph-final-retry.log`                                              |
| 焦点回归       | 残留Tab误用根因已确认；新回归1/1+独立17项+旧逻辑4对照；真实正反遍历10轮全通过，保持post-Enter断言                       | `/private/tmp/knowledge-final-focus-stress.log`、`knowledge-final-focus-review.md`                                       |
| 最后消费复验   | 16/16：审计纠错/冻结历史、融合与PARTIAL隔离、完整建模、C4账户知识及真实试点；最后样式后再补6/6。应用壳/命令面板5/5      | `/private/tmp/knowledge-final-consumers.log`、`knowledge-final-last-business.log`、`knowledge-final-controls-layout.log` |
| 视觉           | 48对、6类真实页×4视口×明暗，同一隔离数据SHA，DPR1/scale1。1440×900、1280×720、768×1024、390×844无页面水平溢出           | `/private/tmp/knowledge-design-system-final/index.html`、`after/manifest.json`、`pair-verification.json`                 |
| 固定列/按钮    | 实际四档表格操作可达、opaque表头及语义分隔；ghost按钮透明、hover/主色按token、两主题通过                                | `/private/tmp/knowledge-final-table-edge.log`、`knowledge-final-button-paint2.log`                                       |
| 最终构建预览   | 独立快照数据、本机8145，登录后六类正式页面通过，页面无错误/水平溢出；后台知识处理关闭                                   | `/private/tmp/knowledge-final-preview-smoke2.log`                                                                        |

默认317项由分批执行组成，成功且不受后续改动影响的证据保留，失败/受影响场景复跑；**不是一次不中断的317/317运行**。没有增加默认timeout/retry或跳过原业务断言。真实API场景使用每轮新临时库，网络故障/缺译分支仅通过受控响应注入；所有图模式矩阵为真实renderer+受控API，不能声称每模式真实生产数据集通过。同数据before/after专用库仅用于只读渲染，未混用于CRUD/失败数据。

### 独立质量复核

Anscombe共享F1–F4、Volta查询/知识草稿R1–R3、James图路径与Tab焦点、James治理只读、Laplace缺译R1–R3及依赖/Vite构建边界均关闭并在相应限定范围PASS。所有Reviewer均是不同于实现者的独立执行者，报告与直接探针可查；报告指纹和范围保留。不把角色改名或主会话自查算独立复核。Volta后续调用曾因上游502失败，治理增量改由James独立完成，保留服务失败记录，不把失败调用当审查。

报告：`knowledge-final-shared-review.md`、`knowledge-final-c4-review.md`、`knowledge-final-graph-review.md`、`knowledge-final-focus-review.md`、`knowledge-final-governance-permission-review.md`、`knowledge-final-i18n-review.md`、`knowledge-final-build-review.md`（均在`/private/tmp`）。

最后增量：截图输出隔离与缺译身份 **4/4** (`knowledge-final-output-and-labels.log`)，最终图谱键盘/手势/检查器/长文 **6/6** (`knowledge-final-graph-last.log`)，图谱label方法Node **10/10**。完整make test之后的这些局部增量按受影响范围复验，未以全量重复替代定向证据。

### 局部验证与未验证

- API没有分页总量的任务/运行使用none及真实前后页；实体集合local，知识库/账号等真正remote。没有伪造total，分页策略详见table.md。
- UI与代码/浏览器校验包含ARIA、键盘与焦点，未进行实体读屏器、物理触摸/笔硬件或全浏览器引擎认证；Chromium协议touch证据与物理设备分开。
- AI使用本机合成模型，未验证外部模型服务质量、远程连接器、生产数据或线上性能。构建数值只描述本机产物，没有性能改善结论。
- 未执行部署、CI、提交/合并、API或后端权限策略改变、历史数据清洗。前端字段缺译/英文留空使用既有schema的可选字段，不改变API和存储格式；冻结内容不回写。
- 原有Pinia devtools peer差异与外层workspace旧开发许可缺口保留在dependencies.md；web172项通过不扩为workspace全闭包准入。

可访问页面：[隔离构建预览](http://127.0.0.1:8145/)、[同数据前后画廊](http://127.0.0.1:5260/)。预览账号为`e2e_admin`，密码`E2E-Admin-Password-2026!`，均为本机合成测试数据；页面服务进程94786、画廊94788可在查验结束后停止。重启方式与限制见preview.md。所有修改保持在当前工作区，未提交。

最终完整浏览器尝试发现任务取消原因旧翻译路径不适配原因码，以及测试夹具记录增多后见证数据被分页隐藏/自动来源无metadata。任务页现区分`tasks.reasons`与统一未知错误；4个中英原因key新增，未知原因保留错误码。真实组件19/19、前端完整701/701通过。测试见证按已知名称搜索，导航预览限定其已采集metadata的真实datasourceId；不全局放行404。稳定源码最终全站分批159+156场通过，2项夹具API超时按原阈值定向复验2/2通过，最终317场全部有完成通过证据。

最终稳定源码浏览器记录：`knowledge-final-all-browser.log`保留159项未受后续任务文案修改影响的完成通过；`knowledge-final-all-browser2.log`为156完成通过；`knowledge-final-all-browser3.log`为最后2项夹具超时复验通过。317项逐项匹配当前catalog，browser-acceptance.json记录每项日志SHA。完整前端任务文案后`knowledge-final-web-tests6.log`701/701；本轮最后代码只改任务原因文案与已授权错误码展示，后端无需再重复已完成1757项。
