# 控件门面契约与消费

> 2026-11-26维护说明：组件契约继续供当前A风格页面复用；尺寸与外观以[tokens](tokens.md)为准。原文的阶段测试结果保留其时间范围，本轮执行见[核验记录](../maintenance/verification-2026-11-26.md)。

本页依据 2026-11-23 当前源码，记录输入、选择、日期、树和导航控件的公开契约。完整共享组件消费表及源码链接见 [components.md](./components.md)；FormContainer / FormField 是统一后的正式名称。状态由页面与受控模型持有，控件不接管请求、权限或路由。

## 公开契约与来源

| 门面                         | 原语与保留契约                                                                                                                                                                                                          | 已核对的真实消费                                       |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| UiInput                      | 官方 shadcn Input；textarea 原生同体系。`value/defaultValue`、`inputProps`、clearable、autosize、password、focus/blur/select/clear/scrollTo。文本更新始终是字符串                                                       | 登录、数据源配置、AI 文档文本与焦点恢复                |
| UiInputNumber                | 原生 number；`number/null`、min/max/precision/step/inputProps；0 不转成空                                                                                                                                               | 数据源端口、关系基数、图谱跳数                         |
| UiSelect                     | Reka Combobox；`value/defaultValue` 保持真实 string/number/null/数组，multiple/filterable/remote/search/loading/clearable；update:value 与 change 携带所选 option，重复同值不发更新                                     | 数据源、关系语义字段、语义视图、资产父级与资源版本选择 |
| UiCheckbox / UiSwitch        | 官方 Checkbox/Switch；checked/value 与对应 default；false 保持布尔值                                                                                                                                                    | 建模授权、数据源/任务配置                              |
| UiRadioGroup / UiRadioButton | Reka RadioGroup；受控 value/defaultValue，原始 string/number；roving focus 由原语处理                                                                                                                                   | 图谱证据查询方式、校验报告范围                         |
| UiTabs / UiTabPane           | Reka Tabs；name/tab、tab 插槽、value/defaultValue。内部编码区分数值名与字符串名；`displayDirective=show` 强制挂载并隐藏非当前内容，状态保留；默认 if 由原语卸载非当前子内容                                             | 本体交换、实体/关系详情、图谱关系抽屉                  |
| UiSlider                     | Reka Slider；number/number[]/null，range、min/max/step、formatTooltip，提交触发 change                                                                                                                                  | 图谱时间回放                                           |
| UiDatePicker                 | 原生 date/datetime-local；模型仍为毫秒 timestamp，date/datetime/daterange/datetimerange；本地日历时间转 epoch，空值为 null；范围未完整时不保留旧有效范围                                                                | 抽取任务计划时间、资产审计时间范围                     |
| UiTree                       | Reka Tree；data/keyField/labelField/childrenField，selected/expanded/checked keys 与 defaults、defaultExpandAll、renderLabel、prefix/suffix、multiple/checkable/cascade；内部编码仅用于原语导航，事件 keys 保留原始类型 | 业务域树与父子域选择                                   |
| UiCollapse / UiCollapseItem  | Reka Accordion；expandedNames/defaultExpandedNames，accordion、name/title/header 插槽、displayDirective                                                                                                                 | 图谱语义配置                                           |

上述控件通过 `useControlField` 消费 FormContainer / FormField 的 disabled/readonly、字段名称、id、帮助与错误属性。
各控件在对应 input/change/blur 事件调用字段校验（以组件声明为准）；复合控件的成员使用原语生成的关联 id，避免把同一个字段 id 复制到所有成员。
输入类型与完整 InputInst 定义在 `inputTypes.ts`；SelectOption/TreeOption 与选择 key 类型定义在 `selectionTypes.ts`。
可访问性、键盘导航和弹层焦点由原语与本地门面共同实现；源码使用这些机制不构成浏览器验收。

## 真实页面与交互入口

| 控件                               | 当前源码消费示例                                                                                                                                                                                                                                                                                |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| UiInput / UiInputNumber / UiSelect | [DataSourcesPage.vue](../../web/src/views/data-integration/sources/DataSourcesPage.vue) 的连接配置；[RelationSemanticFields.vue](../../web/src/views/semantic-assets/relation-types/components/RelationSemanticFields.vue) 的语义字段与基数                                                     |
| UiCheckbox / UiSwitch              | [EntityTypeDetailPage.vue](../../web/src/views/semantic-assets/entity-types/EntityTypeDetailPage.vue)、[AiModelsPage.vue](../../web/src/views/system/ai-models/AiModelsPage.vue)；checkbox 还用于 [ExtractionTasksPage.vue](../../web/src/views/data-integration/tasks/ExtractionTasksPage.vue) |
| UiRadioGroup / UiRadioButton       | [GraphEvidencePage.vue](../../web/src/views/graph/evidence/GraphEvidencePage.vue) 的查询方式、[ValidationReportsPage.vue](../../web/src/views/ontology/validation/ValidationReportsPage.vue) 的报告范围                                                                                         |
| UiTabs / UiTabPane                 | [OntologyExchangePage.vue](../../web/src/views/governance/exchange/OntologyExchangePage.vue)、[GraphEntityDetailPage.vue](../../web/src/views/graph/entities/GraphEntityDetailPage.vue)、[AuditLogsPage.vue](../../web/src/views/system/audit-logs/AuditLogsPage.vue)                           |
| UiSlider                           | [GraphBrowsePage.vue](../../web/src/views/graph/browse/GraphBrowsePage.vue) 的时间回放                                                                                                                                                                                                          |
| UiDatePicker                       | [ExtractionTasksPage.vue](../../web/src/views/data-integration/tasks/ExtractionTasksPage.vue) 的计划时间、[AssetAuditLogs.vue](../../web/src/views/system/audit-logs/components/AssetAuditLogs.vue) 的时间范围                                                                                  |
| UiTree                             | [BusinessDomainsPage.vue](../../web/src/views/semantic-assets/business-domains/BusinessDomainsPage.vue) 的业务域树                                                                                                                                                                              |
| UiCollapse / UiCollapseItem        | [SemanticViewConfig.vue](../../web/src/views/graph/browse/components/SemanticViewConfig.vue) 的语义视图配置                                                                                                                                                                                     |

UiSelect 的 options、选中值和 search 事件独立：remote 跳过本地过滤，由页面更新 options；未加载的选中键显示原始键兜底。清空输出单选 null / 多选空数组，不把 number 0 或 string '0' 混为同一个选项。下拉内容使用 Reka Combobox 的 option 语义，loading/noOptions 使用 role=status。

UiTree 的 selectedKeys、expandedKeys、checkedKeys 独立；事件返回原始 key 类型、对应节点与 meta。defaultExpandAll 不应在刷新数据后重新展开用户已折叠的旧节点。Tabs 的 show 使用 force-mount；默认 if 卸载非当前内容，show:lazy 尚无独立记忆分支。UI 行为与模型身份的测试边界见下节。

UiDatePicker 使用本地日历时间与 epoch milliseconds 转换。range 未完整或倒序时输出 null；内部保留端点草稿。首个输入沿用字段 id，第二个输入追加 -1，范围 aria-label 拼接起止端点文案。

## 默认文案的当前状态

以下值直接核对 [zh-CN.json](../../web/src/locales/zh-CN.json) 和 [en-US.json](../../web/src/locales/en-US.json)，不再作为待添加建议表。

| key                  | zh-CN      | en-US                |
| -------------------- | ---------- | -------------------- |
| ds.clear             | 清空       | Clear                |
| ds.showPassword      | 显示密码   | Show password        |
| ds.hidePassword      | 隐藏密码   | Hide password        |
| ds.selectPlaceholder | 请选择     | Select an option     |
| ds.loading           | 正在加载…  | Loading…             |
| ds.noOptions         | 没有可选项 | No options available |
| ds.dateRange         | 日期范围   | Date range           |
| ds.startDate         | 开始日期   | Start date           |
| ds.endDate           | 结束日期   | End date             |
| ds.expand            | 展开       | Expand               |
| ds.collapse          | 收起       | Collapse             |
| ds.selectItem        | 选择项目   | Select item          |

[UiDatePicker.vue](../../web/src/components/ui/UiDatePicker.vue) 的范围 aria-label 调用 ds.dateRange、ds.startDate 与 ds.endDate。交付前复核两份语言包已包含这三个键；本轮发现的起止端点缺键已由 Chief 补齐。旧报告中的 ds.dateRange 缺键警告也属于历史记录。此处确认源码与文案一致，范围标签的实际可访问性仍由浏览器验收。

## 静态依据与验证边界

契约来源为上述组件、[inputTypes.ts](../../web/src/components/ui/inputTypes.ts)、[selectionTypes.ts](../../web/src/components/ui/selectionTypes.ts) 与 [useControlField.ts](../../web/src/components/ui/useControlField.ts)。现有 [controls.test.mjs](../../web/src/components/ui/__tests__/controls.test.mjs) 覆盖值类型、零/空值、禁用/只读、远程选项、树身份与展开、日期范围、字段标签、Tabs 和 SFC 编译；[controls-harness.mjs](../../web/src/components/ui/__tests__/controls-harness.mjs) 的处理函数与 SSR 检查不等于真实 Reka 键盘、焦点或浏览器布局。

先前阶段记录的 13/13 和临时 TS 配置通过只对应当时文件快照；当前测试源已有后续修改，本页不把旧次数作为当前结果。本轮只检查源码、消费与文档，不重跑组件测试、TS、浏览器或 E2E。主会话据完成日志更新 [verification.md](./verification.md)。

交付重点仍是 Select 键盘/IME/远程搜索/多选清空、字段错误焦点、密码与 textarea、Tree 键盘/勾选、Tabs 动态双语与 show 状态、日期范围/本地时区、明暗主题及禁用/只读；日期范围验收同时核对两端输入的可读标签。
