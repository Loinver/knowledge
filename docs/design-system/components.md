# 组件契约与源码消费

> 2026-11-26维护说明：组件契约继续供当前A风格页面复用；尺寸与外观以[tokens](tokens.md)为准。原文的阶段测试结果保留其时间范围，本轮执行见[核验记录](../maintenance/verification-2026-11-26.md)。

本页以 2026-11-23 的源码核对为依据，覆盖 business 下 10 个共享组件、ui 下 37 个门面及其类型、原语入口和真实消费示例。消费表逐项核对导入与模板 / h() 使用，广泛使用的组件列代表页面，间接组合与测试示例明确标注。运行验收见[核验记录](../maintenance/verification-2026-11-26.md)，本页的静态消费不代表浏览器通过。

领域页面持有 model、请求、路由条件、权限、对象与 revision；共享组件通过输入、事件、插槽和注入协作。维护规则继续使用项目 .agents 正文，本页不另设规范。

## 导入入口与正式契约

统一入口为 [ui/index.ts](../../web/src/components/ui/index.ts)，导出 Ui 门面和 business 组件。表单正式名称为 **FormContainer / FormField**；旧双别名已从 barrel、源码和测试消费中移除，实现仍由原来的两个 business 组件提供。完整类型按下表直接导入项目文件。

| 类型真值源                                                         | 实际定义                                                                                                                              |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| [formTypes.ts](../../web/src/components/ui/formTypes.ts)           | FormRule、FormRules、FormInst、FormContext、FieldContext 与两个 injection key                                                         |
| [inputTypes.ts](../../web/src/components/ui/inputTypes.ts)         | InputValue、InputProps、AutosizeOptions、InputInst；数字解析与本地日期字符串/时间戳转换                                               |
| [selectionTypes.ts](../../web/src/components/ui/selectionTypes.ts) | SelectionKey、SelectValue、SelectOption、TreeOption、TreeSelectMeta；radio/tabs 注入                                                  |
| [tableTypes.ts](../../web/src/components/ui/tableTypes.ts)         | DataTableColumn(s)、DataTableProps、DataTableSlots、SearchTableSlots、PaginationConfig、TableSort、TableFilters、RowKey、RowAction 等 |
| [menuTypes.ts](../../web/src/components/ui/menuTypes.ts)           | MenuOption                                                                                                                            |
| [overlayTypes.ts](../../web/src/components/ui/overlayTypes.ts)     | SheetContext，供 UiDrawer/UiDrawerContent 协作；不是公开 overlay props 汇总                                                           |
| [feedback.ts](../../web/src/components/ui/feedback.ts)             | MessageApi、DialogApi、FeedbackText、DialogOptions、MessageHandle 与 useMessage/useDialog                                             |

barrel 当前只重导出上述类型的一部分；例如 RowKey、RowAction、DataTableSlots 直接从 tableTypes.ts 导入。门面的 props 若没有独立 interface，声明就在对应 Vue 的 defineProps 中。

当前保留的输入与明确边界：

- UiDataTable/SearchTable 只使用 rows、mode、selection；data / remote / checkedRowKeys 输入别名与 update:sorter / update:checkedRowKeys 事件已移除。分页对象仍保留 page/pageSize/itemCount/onChange/onUpdatePage/onUpdatePageSize，顶层受控分页值优先。选择统一发 update:selection(keys, rows, meta)，见 [table.md](./table.md)。
- FormField 的 name、labelFor/labelProps、feedback、validationStatus；FormInst.validate(callback?, paths?) 与 restoreValidation() 仍是现有契约。
- UiButton 的 type 和 text/tertiary/quaternary/secondary/circle、attrType；UiInput 的旧 InputInst 方法；UiModal 的 preset 和 positive/negative 回调入口等兼容声明。
- 部分保留的兼容 props 尚未驱动渲染，限制见后文。后续删除或收缩契约需同步消费方和类型/行为测试；Naive 运行时与表单双别名均已移除。

## FormContainer、FormField 与表单结构

### FormContainer

源码：[FormContainer.vue](../../web/src/components/business/FormContainer.vue)，规则实现：[formValidation.ts](../../web/src/components/business/formValidation.ts)。

真实 props 均可选：model: object、rules: FormRules、disabled、readonly、submitting、labelPlacement、showSummary。rules 默认空对象；showSummary 默认 true。labelPlacement 当前仅声明，未用于表单布局；原生 id/form 等属性通过根 form 的 attrs 接入，没有 formId prop。

FormRules 是按完整字段路径索引的对象：

```ts
type RuleResult = boolean | string | Error | void
type FormRules = Record<string, FormRule | FormRule[]>

// FormRule<T = unknown> 的真实可选项：
interface FormRule<T = unknown> {
  required?: boolean
  type?: 'string' | 'number' | 'integer' | 'boolean' | 'array' | 'object' | 'email' | 'url' | 'date'
  min?: number
  max?: number
  len?: number
  pattern?: RegExp
  message?: string
  trigger?: string | string[]
  validator?(rule: FormRule<T>, value: T): RuleResult | Promise<RuleResult>
}
```

以上形状摘自 formTypes.ts，实际代码直接导入这些类型。validator 接收 rule/value 并返回结果；不是 callback 风格的旧库 validator。类型没有根据 model 自动推导所有合法字段路径。

model 仍由页面和控件的 v-model 持有。这里调用 VeeValidate 的 validate 函数执行本地规则，没有 useForm store、validationSchema prop 或一份额外可写 model。

| 通道             | 准确契约                                                                                                                              |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| expose           | validate(callback?: (errors: Record<string,string> 或 undefined) => void, paths?: string[]): Promise<void>；restoreValidation(): void |
| emits            | submit(event: SubmitEvent)；invalid(errors: Record<string,string>)                                                                    |
| 默认插槽         | errors: Record<string,string>、disabled: disabled 或 readonly 或 submitting                                                           |
| 不存在的具名插槽 | FormContainer 没有 sections/actions/footer 插槽；结构用子组件或默认插槽编排                                                           |

validate() 校验所有 rules 的键；传 paths 则只校验这些键并合并反馈。失败拒绝为 FORM_INVALID，模型/规则代次失效则拒绝为 FORM_CONTEXT_CHANGED；restoreValidation 清错误并失效旧校验。相同完整校验可复用当前 Promise。原生 submit 会先校验，disabled/readonly/submitting 或 submit 校验中不重复发有效 submit；手动 validate() 本身没有 disabled 拒绝条件，按钮保存的权限/请求防重由页面保留。

值读取支持 a.b 和 members[0].name 的数字数组索引；rules 与 Field 的路径字符串必须一致，规则查找不把两种拼写自动合并。空值包含 null/undefined、空白字符串、空数组；0/false 有效。数字规则验证真实 number，date 验证 Date；min/max/len 按数字值或字符串/数组长度判断。未挂载字段仍可能因存在于 rules 而被校验，隐藏字段策略由页面显式调整 rules。

trigger 判断是否启动该字段校验；一旦启动，执行该字段全部规则，不能文档化为逐条只跑匹配 trigger 的规则。

### FormField

源码：[FormField.vue](../../web/src/components/business/FormField.vue)，控件注入：[useControlField.ts](../../web/src/components/ui/useControlField.ts)。

真实 props：path/name、label/help/error、required/disabled/readonly/showFeedback、labelFor/labelProps、validationStatus/feedback。path 优先于 name；showFeedback 默认 true。id 优先使用 labelFor，其次 labelProps.for，再生成稳定 id。

错误取第一个非空值：error → validationStatus 为 error 时的 feedback → FormContext 对应路径错误。错误优先于 help/feedback，即使 showFeedback=false 也显示错误。required 由 prop 或对应规则推导；字段默认不写入 model。

| 插槽     | 实际内容                                                          |
| -------- | ----------------------------------------------------------------- |
| default  | id、aria-labelledby、aria-describedby、aria-invalid、disabled     |
| label    | 替换标签                                                          |
| help     | 替换帮助；未提供时回退 feedback 插槽，再回退 help/feedback 字符串 |
| feedback | 帮助兼容插槽，不覆盖已存在的错误                                  |

readonly/required/validate 等通过 FieldContext 注入 UI 控件，没有在默认插槽额外暴露 readonly/model/value/update。UiInput、UiInputNumber、UiSelect 等调用 useControlField 自动接入 label/error/disabled/readonly；使用原生 input 时需自行绑定插槽属性、值与必要的 readonly/required 语义。

失败焦点由 FormContainer 实现：根据错误结果第一个键查已注册的字段容器，尝试 focus 其中 input/textarea/select/button/[tabindex]。FormField 负责按路径注册与卸载；它自身没有 focus()/validate() expose。不是保证 DOM 顺序中第一个无效字段或必定聚焦 summary；未挂载/不可聚焦控件需要真实浏览器验证。默认插槽始终提供 labelId，原生控件调用方应实际提供可读标签；useControlField 在没有 label 时可省略 aria-labelledby。

### 已存在的结构组件与弹层包装

| 组件 / 源码                                                      | props、emits、slots                                                                                                 | 当前实际消费                                                                                                                                                                                                                                                                                                                                                                                           |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [FormSection](../../web/src/components/business/FormSection.vue) | title?: string；无 emits；默认插槽；fieldset + 可选 legend                                                          | [BaseEditor.vue](../../web/src/views/knowledge/components/BaseEditor.vue)；[GraphLinkForm.vue](../../web/src/views/knowledge/components/GraphLinkForm.vue)                                                                                                                                                                                                                                             |
| [FormActions](../../web/src/components/business/FormActions.vue) | submitting?: boolean；无 emits；默认插槽；只设置操作区域 aria-busy，不自动禁用按钮                                  | [BaseEditor.vue](../../web/src/views/knowledge/components/BaseEditor.vue)；[GraphLinkForm.vue](../../web/src/views/knowledge/components/GraphLinkForm.vue)；[KnowledgeBaseDetailPage.vue](../../web/src/views/knowledge/KnowledgeBaseDetailPage.vue)                                                                                                                                                   |
| [DialogForm](../../web/src/components/business/DialogForm.vue)   | show: boolean、title: string、submitting?: boolean；update:show(boolean)；default/actions                           | [NamespaceCreateModal.vue](../../web/src/views/semantic-assets/components/NamespaceCreateModal.vue)；复用入口：[NamespacesPage.vue](../../web/src/views/semantic-assets/namespaces/NamespacesPage.vue)、[EntityTypesPage.vue](../../web/src/views/semantic-assets/entity-types/EntityTypesPage.vue)、[RelationTypesPage.vue](../../web/src/views/semantic-assets/relation-types/RelationTypesPage.vue) |
| [SheetForm](../../web/src/components/business/SheetForm.vue)     | show: boolean、title: string、submitting?: boolean、width?: number 或 string；update:show(boolean)；default/actions | [BaseEditor.vue](../../web/src/views/knowledge/components/BaseEditor.vue)                                                                                                                                                                                                                                                                                                                              |

DialogForm 组合 UiModal；SheetForm 组合 UiDrawer + UiDrawerContent。actions 被放到内部 footer；没有公开 footer/submit/invalid/model/rules 契约，也不内置 FormContainer 或表单 ref。submitting 关闭 mask/Escape/标题关闭入口；内容字段和按钮的状态仍要传给表单/控件。show 更新交给父层草稿 guard，包装不保存或回滚业务数据。

### i18n 与嵌套字段示例

表单默认必填用 common.required，汇总用 ds.form.invalidSummary。业务 message/label/help 传已经翻译的字符串；rules 放在 computed 中，使 locale 变化可更新消息并触发已有错误重校验。

```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { FormContainer, FormField, FormSection, UiButton, UiInput } from '@/components/ui'
import type { FormInst, FormRules } from '@/components/ui/formTypes'

const { t } = useI18n()
const formRef = ref<FormInst | null>(null)
const draft = ref({ label_i18n: { 'zh-CN': '' } })
const rules = computed<FormRules>(() => ({
  'label_i18n.zh-CN': {
    required: true,
    type: 'string',
    message: t('common.required'),
    trigger: ['blur', 'input'],
  },
}))
function save(_event: SubmitEvent) {
  // 页面捕获对象与 revision 并执行原有保存/迟到响应保护。
}
</script>

<template>
  <FormContainer ref="formRef" :model="draft" :rules="rules" @submit="save">
    <FormSection :title="t('common.label')">
      <FormField path="label_i18n.zh-CN" :label="t('common.labelZh')">
        <UiInput v-model:value="draft.label_i18n['zh-CN']" />
      </FormField>
    </FormSection>
    <UiButton type="primary" attr-type="submit">{{ t('common.save') }}</UiButton>
  </FormContainer>
</template>
```

真实表单示例包括 [BaseEditor.vue](../../web/src/views/knowledge/components/BaseEditor.vue)、[GraphLinkForm.vue](../../web/src/views/knowledge/components/GraphLinkForm.vue)、[LoginPage.vue](../../web/src/views/auth/LoginPage.vue)、[ProfilePage.vue](../../web/src/views/account/ProfilePage.vue)、[GovernanceRulesPage.vue](../../web/src/views/governance/rules/GovernanceRulesPage.vue)、[UsersPage.vue](../../web/src/views/system/users/UsersPage.vue)；这些文件直接消费 FormContainer / FormField。语义资产建模、数据源/任务与本体建模也已统一为同一 FormContainer / FormField 实现。仅需要字段的 [KnowledgeSearchPage.vue](../../web/src/views/knowledge/KnowledgeSearchPage.vue) 与 [AssetAuditLogs.vue](../../web/src/views/system/audit-logs/components/AssetAuditLogs.vue) 直接使用 FormField。

DialogForm 的直接消费者是 NamespaceCreateModal，它被命名空间页、实体类型页、关系类型页复用。该接入把 UiModal 的三项 submitting 关闭控制合并到 DialogForm，并将 footer 内容移至 actions；保存、权限、错误与创建后的选择仍由业务组件持有。SheetForm 的真实消费者仍是 BaseEditor。

## SearchPanel、SearchTable 与表格

### 数据集成页面的真实消费

| 页面                                                                                                                                                                                          | 组件及实际数据能力                                                                                                  | 领域契约                                                                                                |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| [DataSourcesPage.vue](../../web/src/views/data-integration/sources/DataSourcesPage.vue)                                                                                                       | FormContainer/FormField；SearchPanel + SearchTable local，完整列表在本地分页                                        | 新建/编辑身份、动态连接参数、密码原文与空凭据省略由页面持有                                             |
| [ExtractionTasksPage.vue](../../web/src/views/data-integration/tasks/ExtractionTasksPage.vue)                                                                                                 | FormContainer/FormField、UiDatePicker、UiCheckbox；SearchTable none                                                 | 已发布映射 pin、日期毫秒转换、boolean、会话与权限代次由页面持有；数组接口无 total，独立前后页           |
| [ExtractionRunsPage.vue](../../web/src/views/data-integration/runs/ExtractionRunsPage.vue)                                                                                                    | SearchTable none；[RunQuarantine.vue](../../web/src/views/data-integration/runs/components/RunQuarantine.vue) local | 运行页只有真实前后页；隔离记录分页限定当前 run 的完整响应，导出仍使用全量隔离记录                       |
| [DataCatalogPage.vue](../../web/src/views/data-integration/catalog/DataCatalogPage.vue) / [SamplePreviewPage.vue](../../web/src/views/data-integration/catalog/preview/SamplePreviewPage.vue) | SearchTable、UiCard 与统一选择控件                                                                                  | 目录遵循结构快照；样本是当前源数据，none 保留 offset/truncated，无伪 total                              |
| [MappingWorkbenchPage.vue](../../web/src/views/data-integration/mapping/MappingWorkbenchPage.vue)                                                                                             | FormContainer/FormField、UiCard；SearchPanel + SearchTable local                                                    | 嵌套字段路径由领域定义；样本筛选仅作用于当前已读取样本，保留截断说明；工作台持有保存/编译/发布/冻结归属 |

数据源和映射使用外置 SearchPanel 时设 searchable=false，避免双搜索入口。任务/运行/样本预览的 none 模式不截取服务端返回页，不把一页数组长度当作总体数量。UiSelect 选值触发 change，规则需要包含 change 才会立即清除旧字段错误；input 只对应可搜索输入的文本变化。

### SearchPanel

源码：[SearchPanel.vue](../../web/src/components/business/SearchPanel.vue)。

props：query?: string（默认空）、loading?/disabled?/expanded?（expanded 默认 false）、filters?: TableFilters、label?/placeholder?: string。

emits：update:query(string)、update:expanded(boolean)、update:filters(TableFilters)、submit(trim 后的 query, filters 或空对象)、reset()、clear()。Enter 和默认提交按钮通过同一个原生 form submit。loading 只设置 aria-busy，不阻止新输入、提交、清空或重置；disabled 才阻止交互。页面负责取消旧查询、应用条件及重置页码。

| 插槽                         | 准确参数                                                 |
| ---------------------------- | -------------------------------------------------------- |
| filter；未提供时回退 filters | filters、disabled、update(filters)                       |
| advanced                     | filters、disabled、update(filters)；由 expanded 控制展开 |
| actions                      | submit()、clear()、reset()、disabled                     |
| default                      | query、filters、submit()                                 |

clear 发 update:query('') + clear，不附带 submit；reset 只发 reset。默认 label/按钮使用 common.search，clear/reset 使用 ds.search.clear/reset，高级按钮当前使用 kb.advanced。传 label、placeholder 和 actions 插槽可接入现有域文案；没有 searchLabel/autoFetch/debounce 请求函数 prop。

直接页面消费者：[EntityTypesPage.vue](../../web/src/views/semantic-assets/entity-types/EntityTypesPage.vue)、[KnowledgeBaseListPage.vue](../../web/src/views/knowledge/KnowledgeBaseListPage.vue)、[OntologiesPage.vue](../../web/src/views/ontology/ontologies/OntologiesPage.vue)；SearchTable 也可内部组合它。

### UiDataTable 与 SearchTable 的受控契约

源码：[UiDataTable.vue](../../web/src/components/ui/UiDataTable.vue)、[SearchTable.vue](../../web/src/components/business/SearchTable.vue)；完整类型：[tableTypes.ts](../../web/src/components/ui/tableTypes.ts)。UiDataTable 当前使用 TanStack Vue Table v9 的 useTable/tableFeatures 与 core-only 行模型，直接导入 shadcn table 原语。

`DataTableProps<T extends object>` 的实际输入：rows、columns、rowKey/rowProps、mode、total、page/pageSize、pagination、sort、filters、selection、loading/error、initialized、disabled、scrollX/maxHeight、size、bordered、emptyText、label。columns 必填；initialized 默认 true；默认 page=1/pageSize=20/maxHeight=600。bordered 目前只是声明，未用于渲染边框。

`DataTableColumns<T>` 的真实列选项：key/title/render、type:'selection'、format:'number'/'raw'、width/minWidth/maxWidth、fixed:'left'/'right'、align、ellipsis、className/titleClassName、sorter、filter/filterOptions/filterMultiple、disabled。render(row:T,index) 和 cell 插槽保留 T；index 是当前显示集合的索引。没有 group children、expand 列、树行或虚拟滚动契约。

TableSort 为 { columnKey, order:'ascend'/'descend'/false }、其数组或 null。sorter 支持 boolean、default、比较函数或 { compare, multiple? }；多列 local 排序按 multiple 高值优先。TableFilters 按列键保存 string/number/boolean/null 或这些值的数组；local 默认比较保留 0/false/null，支持自定义 filter(value,row)。这些展示控制不决定业务接口的远程排序/筛选能力。

| mode         | 实际处理                                                                                              |
| ------------ | ----------------------------------------------------------------------------------------------------- |
| remote       | 输入是当前页；不二次切片/排序/过滤；数量使用 total 或兼容 pagination.itemCount，不从 rows.length 推算 |
| local        | 调用方明确声明完整集合；对本地副本过滤/排序，并按 page/pageSize 切片；数量取处理后集合长度            |
| none（默认） | 原样展示，不显示分页器，也不执行本地排序/筛选                                                         |

分页状态优先取顶层 page/pageSize，其次 pagination 配置。pagination:false 隐藏分页器；local 仍切片，要完整不分页须用 none。local 夹紧页码后发 update:page；分页/排序/筛选事件由父层更新受控状态，组件不替页面发请求或重置筛选页码。

rowKey 接受业务键函数或字段名，默认读 id；选择列需要 string/number 键，缺失则报错。无选择列、无 id/rowKey 时仅展示可退回 source 索引。number 1 与 string '1' 的选择身份不同；正式业务依赖稳定 rowKey，不依赖显示顺序。

| emits（UiDataTable；SearchTable 同样转发） | 参数                                                                                            |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| update:page / update:pageSize              | number                                                                                          |
| update:sort                                | TableSort                                                                                       |
| update:filters                             | TableFilters                                                                                    |
| update:selection                           | keys: RowKey[]、当前 source 中已加载的对应 rows: `T[]`、meta: SelectionMeta<T> { action, row? } |
| retry                                      | 无参数                                                                                          |
| rowClick                                   | row:T、index:number、MouseEvent 或 KeyboardEvent                                                |

选择只发这一项正式事件；keys 包含跨页选择，rows 只包含当前 source 中已加载且被选中的对象，不伪造其他页对象。meta.action 为 check/uncheck/checkAll/uncheckAll，单行操作附带原 row。全选只修改当前显示页中可选行的键，保留其他页键；禁用行不会被新增或删除，刷新期间选择反馈保留。rowProps 的原生 attrs/事件合并；行 Enter/Space 发 rowClick，嵌套按钮/链接/输入等不触发行操作。

| 表格插槽（`DataTableSlots<T>`）     | 参数                                                      |
| ----------------------------------- | --------------------------------------------------------- |
| toolbar                             | rows:`T[]`、total:number 或 undefined、selection:RowKey[] |
| `cell-<key>`；cell                  | row:T、index、value:unknown、column:`DataTableColumn<T>`  |
| actions                             | row:T、index；仅 actions 列且没有更具体 cell 插槽时使用   |
| error                               | error:string、retry()                                     |
| footer                              | rows:`T[]`、total:number 或 undefined、page:number        |
| empty、initial、loading、refreshing | 无参数                                                    |

error 优先于 empty，有旧 rows 时仍可显示旧行与错误。首次加载和刷新使用 loading/refreshing 插槽；initialized=false 且无数据/错误/加载时使用 initial。页面用 emptyText/empty 插槽区分空库与无匹配，表格不从尚未提交的 query 推断结果语义。

默认 number 单元格使用 Intl.NumberFormat(locale)；字符串机读名/IRI/code 原样显示。数字身份列可 format:raw，显式 render/插槽自行决定格式。长内容留在 DOM，ellipsis 使用 CSS 截断并保留 title；tooltip 配置当前没有独立 Tooltip 渲染。固定列用 sticky，有界滚动不证明所有视口已经验收。

SearchTable 额外 props：query/expanded/searchable/searchLabel/searchPlaceholder，searchable 默认 true。额外 emits 为 update:query、update:expanded、submit(query,filters)、reset、clear；它不额外暴露 FormContainer 模型或请求方法。

表格 loading、error 或 initialized=false 时，toolbar/footer 的 total 为 undefined，分页摘要隐藏数量并禁用翻页，保留请求中的页码。成功的 total=0 仍显示真实零。自定义工具栏应消费 slot 的 total，避免将初始零或旧查询的数量显示成当前结果。

SearchTable 的 search 插槽参数为 query、filters、submit(query,filters)、update(query)；filter/advanced/search-actions 转给内置 SearchPanel；toolbar 可全量替换默认 TableToolbar，toolbar-actions/toolbar-filters 插槽填入默认工具栏。上述表格插槽按声明转发。SearchPanel 的 filters 兼容插槽目前没有被 SearchTable 额外转发，新组合使用 filter 或 search 插槽。

SearchTable 已覆盖语义资产、数据集成、图谱、知识库、治理和系统管理。例如实体/关系类型与数据源用 local；知识库列表、枚举字典、装配模板用 remote；任务/运行/样本页保留 none 与页面原有翻页语义。其他真实消费包括 [GraphEntitiesPage.vue](../../web/src/views/graph/entities/GraphEntitiesPage.vue)、[EvidenceTable.vue](../../web/src/views/graph/components/EvidenceTable.vue)、[KnowledgeBaseDetailPage.vue](../../web/src/views/knowledge/KnowledgeBaseDetailPage.vue)、[GovernanceRulesPage.vue](../../web/src/views/governance/rules/GovernanceRulesPage.vue)、[UsersPage.vue](../../web/src/views/system/users/UsersPage.vue)、[AuditLogsPage.vue](../../web/src/views/system/audit-logs/AuditLogsPage.vue)。这些页面的数据边界以各自传入 mode/rows/total 为准。UiDataTable 还直接服务实体/关系详情、命名空间、业务域和本体列表。

### UiPagination、TableToolbar、RowActions

| 组件                                                               | 准确输入 / 输出 / 插槽                                                                                                                                                                                         | 实际消费者                                                                                                                                                                                                                                                                                                                                                     |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [UiPagination](../../web/src/components/ui/UiPagination.vue)       | page/pageSize/total/itemCount/pageCount、disabled、showSizePicker/pageSizes、label；update:page(number)、update:pageSize(number)、change(page)；summary {total,page,pageSize}、default {page,pageCount,change} | [KnowledgeSearchPage.vue](../../web/src/views/knowledge/KnowledgeSearchPage.vue)；间接：UiDataTable / SearchTable 的分页器                                                                                                                                                                                                                                     |
| [TableToolbar](../../web/src/components/business/TableToolbar.vue) | total?:number、selection?:RowKey[]、loading?/label?；无 emits；summary {total}、selection {keys}、filters/actions/default                                                                                      | [KnowledgeBaseListPage.vue](../../web/src/views/knowledge/KnowledgeBaseListPage.vue)；[KnowledgeBaseDetailPage.vue](../../web/src/views/knowledge/KnowledgeBaseDetailPage.vue)；[DocumentDrawer.vue](../../web/src/views/knowledge/components/DocumentDrawer.vue)；EntityTypesPage 经 SearchTable 间接消费                                                     |
| [RowActions](../../web/src/components/business/RowActions.vue)     | row:T 必填、actions?:`RowAction<T>[]`、disabled?/label?；action(key,row,event)；default {row}                                                                                                                  | [DataSourcesPage.vue](../../web/src/views/data-integration/sources/DataSourcesPage.vue) 通过默认插槽包裹行操作；[KnowledgeBaseListPage.vue](../../web/src/views/knowledge/KnowledgeBaseListPage.vue) 通过 h(RowActions) 的默认插槽保留搜索 RouterLink；测试示例仍见 [table-search.test.mjs](../../web/src/components/business/__tests__/table-search.test.mjs) |

UiPagination 的 total 优先于 itemCount。已知数量/页数时夹紧展示页并发受控纠正事件，disabled 时不纠正；未知 total 且无 pageCount 时保留 page，不制造页数，禁用下一页。默认文案当前用 runs.previous/next/page、assetLedger.resultCount、ui.visible；已经存在 ds.pagination 键不代表此门面已经消费它们。

TableToolbar 的真实 prop 是 label，没有 title。其数量格式化只改变文本，summary 插槽仍得到原始 number total，不根据当前页长度补数量。RowAction 定义见 tableTypes.ts：key/label、可选 onClick(row,event)、disabled:boolean 或函数、loading/destructive；没有 async confirm API，回调调用后再发 action，业务异步状态由消费者控制。

主会话已将 [KnowledgeBaseListPage.vue](../../web/src/views/knowledge/KnowledgeBaseListPage.vue) 的 TableToolbar 调用改为真实 label prop；标题随当前语言渲染。

### i18n 与两种分页消费示例

```vue
<!-- 完整实体集合，本地分页；页面已拥有 loadList 与筛选草稿 -->
<SearchPanel
  v-model:query="searchQuery"
  :label="t('common.search')"
  :loading="loading"
  @submit="loadList"
  @clear="loadList"
  @reset="clearFilters"
/>
<SearchTable
  :rows="filtered"
  :columns="columns"
  :row-key="(row) => row.id"
  mode="local"
  :searchable="false"
  :pagination="{ page, pageSize: 20, onChange: (value) => (page = value) }"
/>
```

```vue
<!-- 知识库当前页；过滤/排序/取消/路由属于页面 -->
<SearchTable
  :rows="current?.items ?? []"
  :total="current?.total"
  :columns="columns"
  :row-key="(row) => row.id"
  :page="filters.page"
  :page-size="20"
  mode="remote"
  :searchable="false"
  :loading="loading"
  :error="error"
  @update:page="filter('page', $event)"
  @retry="reload"
>
  <template #toolbar="{ total }">
    <TableToolbar :label="t('kb.title')" :total="total" :loading="loading" />
  </template>
  <template #empty>
    <UiEmpty :description="t(filters.q ? 'kb.noMatch' : 'kb.emptyBases')" />
  </template>
</SearchTable>
```

列标题/选项标签用 computed(() => [{ title:t(...), ... }])；业务 DTO 从 `api/<domain>` 导入，DataTableColumns 从 ui/tableTypes 导入。render 中数字/日期需自行使用 Intl，技术码保持原值。

## 基础门面：按真实消费分组

以下消费者来自当前静态导入与渲染使用；每个门面均给出真实页面或间接组合链。RowActions 已在 DataSourcesPage 行操作和 KnowledgeBaseListPage 搜索链接两域使用默认插槽，原有动作、权限、请求与 RouterLink 仍由页面持有。每行 Vue 声明是 props 真值源，类型与上游维护指针分别列出。

### 输入、选择和字段交互

| 门面 / 源码                                                                                                                   | 当前契约                                                                                                                                                                                                                                                                                  | 页面消费与上游维护                                                                                                                                                                                                                                                                                                                                                                |
| ----------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [UiInput](../../web/src/components/ui/UiInput.vue)                                                                            | value/defaultValue: string 或 number 或 null，输出 update:value/input/change 为 string；focus/blur、clear；type、inputProps、autosize、rows、maxlength/minlength、disabled/readonly/clearable、placeholder、showPasswordOn；prefix/suffix                                                 | [LoginPage.vue](../../web/src/views/auth/LoginPage.vue)；[BaseEditor.vue](../../web/src/views/knowledge/components/BaseEditor.vue)；[QuickSearch.vue](../../web/src/layout/components/QuickSearch.vue)；InputInst/InputProps 在 inputTypes.ts；input 原语 + 原生 textarea                                                                                                         |
| [UiInputNumber](../../web/src/components/ui/UiInputNumber.vue)                                                                | value/defaultValue:number 或 null；update:value/input/change 保留 number 或 null；min/max/step/precision、disabled/readonly/clearable/inputProps、focus/blur/clear；expose focus/blur；无插槽                                                                                             | [DataSourcesPage.vue](../../web/src/views/data-integration/sources/DataSourcesPage.vue)；[RelationSemanticFields.vue](../../web/src/views/semantic-assets/relation-types/components/RelationSemanticFields.vue)；[KnowledgeSearchPage.vue](../../web/src/views/knowledge/KnowledgeSearchPage.vue)；原生 number input，解析在 inputTypes.ts；showButton 仅声明，无自绘步进按钮契约 |
| [UiSelect](../../web/src/components/ui/UiSelect.vue)                                                                          | SelectValue 为 string/number、其数组或 null；value/defaultValue/options、multiple/filterable/remote/loading/disabled/readonly/clearable、filter(pattern,option)、renderLabel；update:value/change 携带 value 与 option(s) 或 null；search/clear/focus/blur；expose focus/blur；无具名插槽 | [DataSourcesPage.vue](../../web/src/views/data-integration/sources/DataSourcesPage.vue)；[SemanticViewConfig.vue](../../web/src/views/graph/browse/components/SemanticViewConfig.vue)；[KnowledgeBaseListPage.vue](../../web/src/views/knowledge/KnowledgeBaseListPage.vue)；selectionTypes.ts；直接 Reka Combobox，升级时核对 Reka 声明及本地身份编码                            |
| [UiCheckbox](../../web/src/components/ui/UiCheckbox.vue)                                                                      | checked/defaultChecked:boolean、indeterminate、disabled/readonly、value；update:checked/change(boolean)、blur；default 标签插槽                                                                                                                                                           | [BusinessDomainsPage.vue](../../web/src/views/semantic-assets/business-domains/BusinessDomainsPage.vue)；[ExtractionTasksPage.vue](../../web/src/views/data-integration/tasks/ExtractionTasksPage.vue)；[GraphBrowsePage.vue](../../web/src/views/graph/browse/GraphBrowsePage.vue)；checkbox 原语                                                                                |
| [UiSwitch](../../web/src/components/ui/UiSwitch.vue)                                                                          | value/defaultValue:boolean、disabled/readonly/loading；update:value/change(boolean)、blur；checked/unchecked 插槽                                                                                                                                                                         | [EntityTypeDetailPage.vue](../../web/src/views/semantic-assets/entity-types/EntityTypeDetailPage.vue)；[AiModelsPage.vue](../../web/src/views/system/ai-models/AiModelsPage.vue)；switch 原语                                                                                                                                                                                     |
| [UiRadioGroup](../../web/src/components/ui/UiRadioGroup.vue) / [UiRadioButton](../../web/src/components/ui/UiRadioButton.vue) | Group value/defaultValue:string/number/null、disabled/readonly/name，update:value/change(T)、blur、default；Button value 必填、disabled/readonly/label、default                                                                                                                           | [GraphEvidencePage.vue](../../web/src/views/graph/evidence/GraphEvidencePage.vue)；[ValidationReportsPage.vue](../../web/src/views/ontology/validation/ValidationReportsPage.vue)；直接 Reka RadioGroup；selectionTypes.ts 注入 group 状态                                                                                                                                        |
| [UiDatePicker](../../web/src/components/ui/UiDatePicker.vue)                                                                  | value/defaultValue:number 或 number[] 或 null；type=date/datetime/daterange/datetimerange；update:value/change(T)、clear/blur；disabled/readonly/clearable/inputProps；无插槽                                                                                                             | [ExtractionTasksPage.vue](../../web/src/views/data-integration/tasks/ExtractionTasksPage.vue)；[AssetAuditLogs.vue](../../web/src/views/system/audit-logs/components/AssetAuditLogs.vue)；原生 date/datetime-local + inputTypes.ts 本地日历转换，无 shadcn Calendar 原语契约                                                                                                      |
| [UiSlider](../../web/src/components/ui/UiSlider.vue)                                                                          | value/defaultValue:number 或 number[] 或 null；range/min/max/step/disabled/readonly/vertical、formatTooltip(value)；update:value/change(T)、blur；无插槽                                                                                                                                  | [GraphBrowsePage.vue](../../web/src/views/graph/browse/GraphBrowsePage.vue)；直接 Reka Slider                                                                                                                                                                                                                                                                                     |

UiInput 的 value 输入可接受 number，但输出仍为 string；未传 value 才使用本地 defaultValue。maxlength 等原生限制、inputProps 和 attrs 透传到实际输入；Field 注入属性最后合并。InputInst 除 focus/blur/select/clear 还保留 activate/deactivate/scrollTo 与 DOM ref、isCompositing 兼容成员。

UiSelect 在 remote 模式跳过本地过滤，search 事件不发请求。当前已选键不在 options 时显示原始键兜底；clear 返回单选 null/多选空数组。options label、renderLabel 可由页面提供已翻译字符串或 VNode，number 与 string 键不混淆。

UiDatePicker 的 number 是 epoch milliseconds；输入按本地日历时间解析，未完整/倒序 range 发 null，保留两端编辑草稿。不是 ISO 字符串或日期对象输出。UiSlider 默认显示可拖范围不表示 null 已被业务提交；自定义值说明走 formatTooltip。

### 导航型控件和树

| 门面 / 源码                                                                                                                 | 当前契约                                                                                                                                                                                                                                   | 页面消费与上游维护                                                                                                                                                                                                                                                                                                    |
| --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [UiTabs](../../web/src/components/ui/UiTabs.vue) / [UiTabPane](../../web/src/components/ui/UiTabPane.vue)                   | Tabs value/defaultValue:SelectionKey、disabled/readonly、placement；update:value/change；default/suffix。Pane name 必填，tab:string/number/函数，disabled/readonly/displayDirective，default；tab 插槽由 Tabs 从 Pane VNode 子插槽读取     | [OntologyExchangePage.vue](../../web/src/views/governance/exchange/OntologyExchangePage.vue)；[EntityTypeDetailPage.vue](../../web/src/views/semantic-assets/entity-types/EntityTypeDetailPage.vue)；[AuditLogsPage.vue](../../web/src/views/system/audit-logs/AuditLogsPage.vue)；直接 Reka Tabs + selectionTypes.ts |
| [UiTree](../../web/src/components/ui/UiTree.vue)                                                                            | data:TreeOption[]、keyField/labelField/childrenField；selected/expanded/checkedKeys 与各 default*、defaultExpandAll；selectable/multiple/checkable/cascade、disabled/readonly；renderLabel；update:*Keys 含 keys/options/meta；无公开 slot | [BusinessDomainsPage.vue](../../web/src/views/semantic-assets/business-domains/BusinessDomainsPage.vue)；直接 Reka Tree + checkbox 原语；TreeOption/TreeSelectMeta 在 selectionTypes.ts                                                                                                                               |
| [UiCollapse](../../web/src/components/ui/UiCollapse.vue) / [UiCollapseItem](../../web/src/components/ui/UiCollapseItem.vue) | expandedNames/defaultExpandedNames:SelectionKey 或数组或 null、accordion、disabled/readonly；update:expandedNames；default。Item name 必填、title/disabled/readonly/displayDirective，default/header                                       | [SemanticViewConfig.vue](../../web/src/views/graph/browse/components/SemanticViewConfig.vue)；实际直接使用 Reka Accordion，不能按名称误记为 Collapsible 实现                                                                                                                                                          |

Tree 使用业务 key 的类型化编码，checkedKeys 与 selectedKeys 独立；cascade 递归处理允许选择的子节点，禁用节点不随操作变更。原语 API 不等于领域树身份或权限验收。

TabPane 默认 displayDirective=if；show 使用 force-mount，show:lazy 当前没有独立 lazy 记忆分支。Pane 的 readonly 未用于父 TabsTrigger 禁用，锁定导航要传给 Tabs。Tabs 的 type/size/animated 目前仅兼容声明；placement 的 left/right 实际决定 vertical。CollapseItem 的 show 使用 force-mount。

### 弹层、确认和反馈

| 门面 / 源码                                                                                                                       | 当前契约                                                                                                                                                                                                                       | 页面消费与上游维护                                                                                                                                                                                                                                                                                                                     |
| --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [UiModal](../../web/src/components/ui/UiModal.vue)                                                                                | show/title/content、closable/maskClosable/closeOnEsc、positiveText/negativeText、positiveButtonProps、restoreFocusTo、onPositiveClick/onNegativeClick；update:show/close/after-enter/after-leave；default/action/footer        | [QuickSearch.vue](../../web/src/layout/components/QuickSearch.vue)；[UsersPage.vue](../../web/src/views/system/users/UsersPage.vue)；[DataSourcesPage.vue](../../web/src/views/data-integration/sources/DataSourcesPage.vue)；间接：DialogForm → NamespaceCreateModal；dialog 原语 + Reka DialogContent/Overlay                        |
| [UiDrawer](../../web/src/components/ui/UiDrawer.vue) / [UiDrawerContent](../../web/src/components/ui/UiDrawerContent.vue)         | Drawer show/width/height/placement/showMask/maskClosable/closeOnEsc/trapFocus/blockScroll；update:show/after-enter/after-leave；default。Content title/closable/bodyContentStyle；default/header/footer；没有自己的 close emit | [GovernanceRulesPage.vue](../../web/src/views/governance/rules/GovernanceRulesPage.vue)；[DocumentDrawer.vue](../../web/src/views/knowledge/components/DocumentDrawer.vue)；[EvidenceDrawer.vue](../../web/src/views/knowledge/components/EvidenceDrawer.vue)；间接：SheetForm → BaseEditor；sheet 原语 + Reka Dialog；overlayTypes.ts |
| [UiPopover](../../web/src/components/ui/UiPopover.vue)                                                                            | show/disabled/width，update:show；default/trigger；trigger/placement 有声明                                                                                                                                                    | 间接：[UiPopconfirm.vue](../../web/src/components/ui/UiPopconfirm.vue) → [NamespacesPage.vue](../../web/src/views/semantic-assets/namespaces/NamespacesPage.vue)；popover 原语 + Reka Content/Portal；当前没有根据 trigger 实现 hover/manual 分支或根据 placement 配置定位                                                             |
| [UiPopconfirm](../../web/src/components/ui/UiPopconfirm.vue)                                                                      | positiveText/negativeText、disabled、showIcon、onPositiveClick/onNegativeClick；default/trigger；内部拥有 show，不提供 update:show expose/emits                                                                                | [NamespacesPage.vue](../../web/src/views/semantic-assets/namespaces/NamespacesPage.vue)；[GovernanceRulesPage.vue](../../web/src/views/governance/rules/GovernanceRulesPage.vue)；[DocumentDrawer.vue](../../web/src/views/knowledge/components/DocumentDrawer.vue)；UiPopover + UiButton，无独立 confirm 原语                         |
| [UiDropdown](../../web/src/components/ui/UiDropdown.vue)                                                                          | options:MenuOption[] 必填；select(key)；default 是 trigger 内容；trigger 仅声明                                                                                                                                                | [UserDropdown.vue](../../web/src/layout/components/UserDropdown.vue)；间接：UiPopselect → GraphBrowsePage；dropdown-menu 原语；当前菜单逐项平铺，不递归 MenuOption.children，也没有完整 group/submenu 实现                                                                                                                             |
| [UiPopselect](../../web/src/components/ui/UiPopselect.vue)                                                                        | options[{label,value,disabled?}] 必填，update:value(string/number)，default；trigger 仅声明                                                                                                                                    | [GraphBrowsePage.vue](../../web/src/views/graph/browse/GraphBrowsePage.vue)；组合 UiDropdown，没有受控 value prop 或远程选项请求                                                                                                                                                                                                       |
| [UiFeedbackProvider](../../web/src/components/ui/UiFeedbackProvider.vue) / [feedback.ts](../../web/src/components/ui/feedback.ts) | Provider default；useMessage().success/error/warning/info(text 或函数, {duration?}) → destroy handle；useDialog().warning(DialogOptions) → destroy handle                                                                      | [App.vue](../../web/src/App.vue)；消费者需位于 Provider 内；直接 Reka Toast + UiModal                                                                                                                                                                                                                                                  |

Modal 的 show 是受控输入，preset 当前不改变渲染。positive/negative 回调返回 false 会保留打开，reject 显示 ds.actionFailed；内部会话代次隔离旧动作回调。after-enter/leave 当前在 nextTick 后通知状态转换，不是 CSS 动画结束承诺。DialogForm 使用 show，不是 open。

Drawer 的 title 由 Content 注入，Drawer 没有 title prop。modal 实际取 showMask && trapFocus && blockScroll；这些不是三个已经独立验证的滚动/焦点开关。草稿 guard 仍由页面决定是否接受 update:show(false)。

Popconfirm 以回调 props 接收动作，不能文档化为已经声明 confirm/cancel/positive-click emits；Vue 模板的 @positive-click 映射到回调 prop。showIcon 当前仅声明。

### 展示、状态和结构

| 门面 / 源码                                                                                                                                 | 当前契约                                                                                                                                | 实际消费者与维护归属                                                                                                                                                                                                                                                                                                                                                      |
| ------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [UiButton](../../web/src/components/ui/UiButton.vue)                                                                                        | variant、type、size、attrType、disabled/loading、block 与兼容变体；default/icon；click 是根 Button 的原生事件透传，没有单独 defineEmits | [DashboardPage.vue](../../web/src/views/dashboard/DashboardPage.vue)；[LoginPage.vue](../../web/src/views/auth/LoginPage.vue)；[AppHeader.vue](../../web/src/layout/components/AppHeader.vue)；button 原语                                                                                                                                                                |
| [UiAlert](../../web/src/components/ui/UiAlert.vue)                                                                                          | type/title/showIcon/closable；close；default/header；error 时 role=alert                                                                | [SecurityPage.vue](../../web/src/views/account/SecurityPage.vue)；[DashboardPage.vue](../../web/src/views/dashboard/DashboardPage.vue)；[KnowledgeBaseListPage.vue](../../web/src/views/knowledge/KnowledgeBaseListPage.vue)；本地状态展示，没有导入 shadcn Alert                                                                                                         |
| [UiSpin](../../web/src/components/ui/UiSpin.vue)                                                                                            | show/description/size；default；保留内容并覆盖 loading status                                                                           | [DashboardPage.vue](../../web/src/views/dashboard/DashboardPage.vue)；[ValidationReportsPage.vue](../../web/src/views/ontology/validation/ValidationReportsPage.vue)；[KnowledgeSearchPage.vue](../../web/src/views/knowledge/KnowledgeSearchPage.vue)；本地结构，size 仅声明                                                                                             |
| [UiEmpty](../../web/src/components/ui/UiEmpty.vue)                                                                                          | description/size；default/icon/extra；默认 ds.empty                                                                                     | [OntologyHistory.vue](../../web/src/views/governance/exchange/components/OntologyHistory.vue)；[KnowledgeBaseListPage.vue](../../web/src/views/knowledge/KnowledgeBaseListPage.vue)；[QuickSearch.vue](../../web/src/layout/components/QuickSearch.vue)；本地结构，size 仅声明                                                                                            |
| [UiTag](../../web/src/components/ui/UiTag.vue)                                                                                              | type/round 实际驱动语义色/圆角，size/bordered 兼容声明；default                                                                         | [EvidenceTable.vue](../../web/src/views/graph/components/EvidenceTable.vue)；[DocumentStatus.vue](../../web/src/views/knowledge/components/DocumentStatus.vue)；[RolesPage.vue](../../web/src/views/system/roles/RolesPage.vue)；badge 原语                                                                                                                               |
| [UiSpace](../../web/src/components/ui/UiSpace.vue)                                                                                          | vertical/wrap/size:number/string/[number,number]、align/justify；default                                                                | [OntologyExchangePage.vue](../../web/src/views/governance/exchange/OntologyExchangePage.vue)；[RelationSemanticFields.vue](../../web/src/views/semantic-assets/relation-types/components/RelationSemanticFields.vue)；[UsersPage.vue](../../web/src/views/system/users/UsersPage.vue)；本地 flex/语义 token，不是 Stack 原语                                              |
| [UiCard](../../web/src/components/ui/UiCard.vue)                                                                                            | title/bordered/contentStyle；size 仅声明；default/header/header-extra/footer                                                            | [MappingWorkbenchPage.vue](../../web/src/views/data-integration/mapping/MappingWorkbenchPage.vue)；[SamplePreviewPage.vue](../../web/src/views/data-integration/catalog/preview/SamplePreviewPage.vue)；[OntologyHistory.vue](../../web/src/views/governance/exchange/components/OntologyHistory.vue)；card 原语                                                          |
| [UiDescriptions](../../web/src/components/ui/UiDescriptions.vue) / [UiDescriptionsItem](../../web/src/components/ui/UiDescriptionsItem.vue) | column/title、bordered/size 兼容声明；default。Item label/span；default/label                                                           | [EntityTypeDetailPage.vue](../../web/src/views/semantic-assets/entity-types/EntityTypeDetailPage.vue)；[OntologyHistory.vue](../../web/src/views/governance/exchange/components/OntologyHistory.vue)；[EnumDictionariesPage.vue](../../web/src/views/semantic-assets/configuration/enum-dictionaries/EnumDictionariesPage.vue)；本地 dl/dt/dd，不是上游 descriptions 原语 |
| [UiTable](../../web/src/components/ui/UiTable.vue)                                                                                          | default 自编排 thead/tbody；attrs 传给原生 table；size/bordered/singleLine 仅声明                                                       | [ValidationReportsPage.vue](../../web/src/views/ontology/validation/ValidationReportsPage.vue)；[FrozenMapping.vue](../../web/src/views/data-integration/mapping/components/FrozenMapping.vue)；[TemplateCoreCheck.vue](../../web/src/views/semantic-assets/configuration/assembly-templates/components/TemplateCoreCheck.vue)；本地静态表格，不带 DataTable 行模型/分页  |
| [UiDivider](../../web/src/components/ui/UiDivider.vue)                                                                                      | vertical；没有插槽                                                                                                                      | [AiModeling.vue](../../web/src/views/ontology/designer/components/modeling/AiModeling.vue)；separator 原语                                                                                                                                                                                                                                                                |
| [UiList](../../web/src/components/ui/UiList.vue) / [UiListItem](../../web/src/components/ui/UiListItem.vue)                                 | List bordered + default；Item default，没有 props                                                                                       | [AiSuggestions.vue](../../web/src/views/ontology/designer/components/AiSuggestions.vue)；本地 ul/li                                                                                                                                                                                                                                                                       |

UiButton 的 type 是语义变体，原生 submit/reset 必须用 attrType。loading 实际禁用按钮；搜索期间需要可重新提交时，SearchPanel 默认原生按钮只设置 aria-busy，不能额外用 UiButton.loading 将整个搜索操作锁住。

## 原语维护与 i18n 接入指针

上游缓存位于 [ui/primitives](../../web/src/components/ui/primitives)：每个实际缓存组有 index.ts、Vue 源码和 upstream.registry。registry 是原始导入响应；本地 Vue 已有 token/i18n/类型/交互适配。升级比较上游与本地差异后保留这些适配，不能直接用缓存或 CLI 输出覆盖现有源码。

| 已读维护入口                                                                                                                                                                                                         | 当前角色                                                                                   |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| [button/index.ts](../../web/src/components/ui/primitives/button/index.ts)、[button/upstream.registry](../../web/src/components/ui/primitives/button/upstream.registry)                                               | Button 与 buttonVariants/ButtonVariants；UiButton 在其上适配语义变体                       |
| [field/index.ts](../../web/src/components/ui/primitives/field/index.ts)、[field/upstream.registry](../../web/src/components/ui/primitives/field/upstream.registry)                                                   | Field/Label/Description 等结构；表单规则与错误路径在 business/FormContainer/FormField      |
| [table/index.ts](../../web/src/components/ui/primitives/table/index.ts)、[table/upstream.registry](../../web/src/components/ui/primitives/table/upstream.registry)                                                   | Table/Head/Cell/Row 等；Table 门面不等于 UiDataTable 的受控状态                            |
| [dialog/DialogContent.vue](../../web/src/components/ui/primitives/dialog/DialogContent.vue)、[sheet/SheetContent.vue](../../web/src/components/ui/primitives/sheet/SheetContent.vue)                                 | Reka Dialog 的本地关闭按钮/token/i18n 适配                                                 |
| [pagination/PaginationNext.vue](../../web/src/components/ui/primitives/pagination/PaginationNext.vue)、[pagination/PaginationPrevious.vue](../../web/src/components/ui/primitives/pagination/PaginationPrevious.vue) | 原语默认 next/previous 文案；UiPagination 当前有自己的原生 nav 实现，不能把两者 props 合并 |
| [utils.ts](../../web/src/components/ui/utils.ts)                                                                                                                                                                     | cn 从 cn 包导出；usePrimitiveI18n 绑定全局 ds.primitives.*                                 |
| [THIRD_PARTY_LICENSES.md](../../web/src/components/ui/THIRD_PARTY_LICENSES.md)                                                                                                                                       | 保留许可证文本；具体版本/来源 hash 指向现有 dependencies 文档，本轮不做许可/依赖验收       |

其他实际使用缓存组为 input、checkbox、switch、badge、card、popover、dropdown-menu、separator；每组的本地入口/缓存按同名目录查找。radio/tabs/tree/slider/accordion/combobox 门面直接使用 Reka，相应声明位于安装包；仓库同时存在部分同名 shadcn 缓存不表示门面已经使用它。toast 当前直接使用 Reka，不虚构未存在的 primitives/toast 目录。

usePrimitiveI18n 的调用方式：

```ts
import { usePrimitiveI18n } from '@/components/ui/utils'
const { t: primitiveText } = usePrimitiveI18n()
// primitiveText('close') → 全局 ds.primitives.close
// 允许键为 close/first/last/next/previous/more
```

业务/门面用 vue-i18n 的 t 传 label、title、option label、rules.message；运行时 locale 变化需要 computed 标签/规则，长寿命通知可以传 () => t('...') 使 FeedbackText 在渲染时求值。UiFeedbackProvider 必须先安装，否则 useMessage/useDialog 会抛错。语言包是唯一默认消息来源；本轮只核对现有键，不新建局部 messages 或修改 locale 文件。

## 源码证据与交接边界

本页逐项以 ui/index.ts、business/ui 的 props/emits/expose/slots、类型文件和页面导入及模板 / h() 调用核对。App.vue 安装 UiFeedbackProvider；[UserDropdown.vue](../../web/src/layout/components/UserDropdown.vue) 使用 useDialog / useMessage，[ProfilePage.vue](../../web/src/views/account/ProfilePage.vue)、[SecurityPage.vue](../../web/src/views/account/SecurityPage.vue) 等使用 useMessage。测试 harness 不计为页面消费者。

本轮只更新文档并检查链接、格式、契约与引用；没有运行产品测试或浏览器。RowActions 的两域真实消费已静态核对；测试示例、组件实现与原语行为均不等于页面验收，实际结果由 Chief 记录。仅声明的 props、隐藏字段错误焦点、键盘/IME/弹层焦点、跨页选择和迟到响应仍需主会话根据实际测试结果验收。

交付同步点：FormContainer / FormField 已统一正式名称，后续契约调整同步入口、页面、harness 与示例；表格事件和类型消费夹具按 [table.md](./table.md) 核对；日期范围语言键已补齐，当前状态见 [controls.md](./controls.md)。组件新增或替换消费时同时更新对应消费行。
