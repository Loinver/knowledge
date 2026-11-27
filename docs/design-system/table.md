# 表格与搜索共享契约

> 2026-11-26维护说明：组件契约继续供当前A风格页面复用；尺寸与外观以[tokens](tokens.md)为准。原文的阶段测试结果保留其时间范围，本轮执行见[核验记录](../maintenance/verification-2026-11-26.md)。

本页以 2026-11-23 当前 [tableTypes.ts](../../web/src/components/ui/tableTypes.ts)、[UiDataTable.vue](../../web/src/components/ui/UiDataTable.vue) 和 [SearchTable.vue](../../web/src/components/business/SearchTable.vue) 为依据。表格只管理展示与受控交互；请求、路由、权限、对象/revision 和旧请求失效由页面持有。组件消费总表见 [components.md](./components.md)。

## 正式输入与数据边界

`DataTableProps<T>` 使用 rows、columns、rowKey/rowProps、mode、total、page/pageSize、pagination、sort、filters、selection、loading/error、initialized、disabled、scrollX/maxHeight、size、bordered、emptyText、label。columns 必填，其余可选；默认 mode=none、page=1、pageSize=20、initialized=true。bordered 当前仅声明。

`data`、`remote`、`checkedRowKeys` 输入别名已删除；`update:sorter`、`update:checkedRowKeys` 事件已删除。分页配置的 `itemCount`、`onChange`、`onUpdatePage`、`onUpdatePageSize` 仍有定义，不能因清理表格别名而一并删去。

| mode         | rows 的含义与实际处理                           | 数量与分页                                                      |
| ------------ | ----------------------------------------------- | --------------------------------------------------------------- |
| remote       | 当前服务端页；不再次切片、排序或筛选            | 使用 total 或 pagination.itemCount，不能用 rows.length 冒充总量 |
| local        | 调用方明确提供完整集合；对副本筛选/排序，再分页 | 处理后集合长度为总量；不修改输入数组                            |
| none（默认） | 原样展示，不运行本地排序/筛选                   | 不显示分页器，不推导远程数量                                    |

顶层 page/pageSize 优先于 pagination 对象。pagination=false 隐藏分页器，但 local 仍执行切片；完整展示集合使用 none。成功的 total=0 保留真实零；未知 total 不制造页数。排序/筛选/翻页事件不自动发送请求，也不替页面重置 page。

## 列、排序与行身份

项目列类型为 `DataTableColumns<T>`，业务 DTO 继续从 `api/<domain>` 导入。列支持 key/title/render、type=selection、format、width/minWidth/maxWidth、align、fixed、ellipsis、className/titleClassName、sorter、filter/filterOptions/filterMultiple、disabled。render(row, index) 与 cell 插槽保留业务 T；没有树行、展开行、分组列或虚拟滚动契约。

rowKey 是业务 string/number 键函数或字段名，默认读取 id。选择列必须能解析稳定 string/number 键，否则显式报错；number 1 与 string '1' 保持不同身份。无选择列且无 id/rowKey 时仅展示可退回 source 索引，正式消费者仍应提供稳定键。

sort 为 `{ columnKey, order: 'ascend' | 'descend' | false }`、其数组或 null。单列点击在升序/降序/取消间切换；sorter 支持默认比较、函数或 `{ compare, multiple }`，local 多列排序按 multiple 高值优先。remote/none 不执行 comparator。

filters 保存列键到 string/number/boolean/null 或数组的映射；local 使用严格值比较或自定义 filter(value, row)，保留 0/false/null。remote 只发 `update:filters`，由页面映射接口能力。

默认 number 单元格按当前 locale 用 Intl.NumberFormat 展示；字符串机读码/IRI 原样保留，数字身份可设 format=raw。显式 render/插槽由消费者决定格式。长内容留在 DOM，ellipsis 仅视觉截断并保留 title；固定列使用 sticky，布局仍需浏览器核验。

## 唯一选择事件与受控输出

UiDataTable 和 SearchTable 使用相同的正式事件：

| 事件                          | 参数                                               |
| ----------------------------- | -------------------------------------------------- |
| update:page / update:pageSize | number                                             |
| update:sort                   | TableSort                                          |
| update:filters                | TableFilters                                       |
| update:selection              | keys: RowKey[]、rows: T[]、meta: SelectionMeta<T>  |
| rowClick                      | row: T、index: number、MouseEvent 或 KeyboardEvent |
| retry                         | 无参数                                             |

`update:selection(keys, rows, meta)` 是单一事件，SearchTable 将三个参数完整转发：

- keys 是完整的受控选择键集合，包括跨页选择，保留原始 number/string 类型。
- rows 仅是当前 source 中与 keys 对应的已加载业务对象；不补造未加载页对象，也不承诺与 keys 等长。
- meta.action 是 check/uncheck/checkAll/uncheckAll；单行操作附带原 row。

全选仅改变当前展示页的可选行，保留其他页和禁用行已有的键。loading/disabled 时阻止修改，刷新保留原 checkbox 反馈。`v-model:selection` 消费第一个 keys 参数；需要完整载荷的调用方使用显式事件处理器。

```vue
<UiDataTable
  :rows="items"
  :columns="columns"
  :row-key="(row) => row.id"
  mode="local"
  :selection="selection"
  v-model:sort="sort"
  @update:selection="(keys, rows, meta) => onSelection(keys, rows, meta)"
/>
```

rowProps 的原生属性/事件与 rowClick 合并。行 Enter/Space 可触发 rowClick；嵌套 button/link/input/select 等交互控件不会触发行操作。权限与危险操作确认仍由页面处理。

## 搜索、工具栏与分页组合

[SearchPanel.vue](../../web/src/components/business/SearchPanel.vue) 的 query/expanded/filters 受控；事件为 update:query、update:expanded、update:filters、submit(trim 后 query, filters)、reset、clear。Enter 与默认按钮共用原生 form submit。loading 只提供 aria-busy，允许输入、提交另一查询、清空和重置；disabled 才阻止这些动作。页面使用 AbortController 或原有代次保护使旧请求失效。

clear 发 update:query('') + clear，不隐式 submit；reset 只发 reset。filter（兼容 filters）、advanced、actions、default 插槽提供状态与更新/提交回调，不接受业务请求函数。

SearchTable 组合 SearchPanel、TableToolbar、UiDataTable 与其分页器，增加 query/expanded/searchable/searchLabel/searchPlaceholder 输入。searchable 默认 true；外置 SearchPanel 的页面设为 false。search 插槽提供 query/filters/submit/update；filter、advanced、search-actions 转发到内部搜索，toolbar 可替换整个默认工具栏，toolbar-actions/toolbar-filters 填充相应位置。SearchPanel 的 filters 兼容插槽不额外转发。

[TableToolbar.vue](../../web/src/components/business/TableToolbar.vue) 接收 total、selection、loading、label，提供 summary、selection、filters、actions、default 插槽；没有 title prop。total 与选择 key 的类型不因文本格式化而改变，也不由当前页长度推算总量。

[RowActions.vue](../../web/src/components/business/RowActions.vue) 接收 row 与 actions，action(key, row, event) 保留业务对象；支持 disabled/loading/destructive，业务异步状态仍由调用方持有。真实消费为 DataSourcesPage 的行操作插槽和 KnowledgeBaseListPage 的搜索链接；组件示例在 [table-search.test.mjs](../../web/src/components/business/__tests__/table-search.test.mjs) 的 row actions 用例。

[UiPagination.vue](../../web/src/components/ui/UiPagination.vue) 接收 total/itemCount（total 优先）、pageCount、page/pageSize、disabled、pageSizes/showSizePicker、label；发 update:page、update:pageSize 与 change(page)。已知数量时夹紧展示页并发受控纠正，disabled 时不纠正。未知总量且无 pageCount 时保留传入 page，可回上一页，禁用下一页，不显示总数。

## 状态与插槽

| 插槽                                   | 参数/语义                                                  |
| -------------------------------------- | ---------------------------------------------------------- |
| cell-<key> / cell                      | row、index、value、column；具体单元格优先于通用插槽/render |
| actions                                | row、index；用于 actions 列且没有更具体 cell 插槽时        |
| toolbar                                | rows、total、selection                                     |
| footer                                 | rows、total、page                                          |
| error                                  | error、retry()                                             |
| initial / empty / loading / refreshing | 无参数；区分初次查询、空结果、首次加载和保留旧行的刷新     |

error 优先于 empty，有旧 rows 时可同时显示旧行和错误。initialized=false、无行/错误/加载时显示 initial；页面通过 emptyText 或 empty 插槽区分空库与无匹配，不从尚未提交的 query 推断结果语义。

loading、error 或 initialized=false 时，toolbar/footer 的 total 为 undefined，分页隐藏数量、禁用翻页并保留请求中的页码；成功结果的零总量仍为零。自定义工具栏应使用 slot.total，避免把旧查询数量显示成新查询结果。

```vue
<SearchTable
  :rows="current?.items ?? []"
  :total="current?.total"
  :columns="columns"
  :row-key="(row) => row.id"
  mode="remote"
  :page="page"
  :page-size="20"
  :loading="loading"
  :error="error"
  v-model:query="query"
  @submit="applyQuery"
  @update:page="changePage"
  @retry="reload"
>
  <template #toolbar="{ total }">
    <TableToolbar :label="t('kb.title')" :total="total" :loading="loading" />
  </template>
</SearchTable>
```

默认文案以当前源码为准：SearchPanel 已使用 ds.search.clear/reset；UiPagination 仍使用 runs.previous/next/page、assetLedger.resultCount、ui.visible；选择 label 使用 ui.selected，initial 使用 common.search。ds.pagination._、ds.table._ 虽已存在于双语资源，不代表门面已消费。页面可传 label、emptyText、插槽接入领域文案。

## 真实消费与静态验收边界

完整实体/关系类型列表与数据源使用 local；知识库列表、枚举字典和装配模板使用 remote；任务、运行、样本页保留 none 与原有前后页/offset/truncated 语义。图谱、治理、系统管理及知识库详情也已使用 SearchTable，具体入口见 [components.md](./components.md)。直接分页消费者包括 [KnowledgeSearchPage.vue](../../web/src/views/knowledge/KnowledgeSearchPage.vue)。

[table-search.test.mjs](../../web/src/components/business/__tests__/table-search.test.mjs) 保留远程不二次处理、local 边界、零/未知数量、原始类型、跨页身份、禁用、排序、状态、请求替换及完整选择载荷的断言。该测试使用 Vue 自定义 renderer，源码检查只能确认断言与正式事件存在；本轮文档工作未运行测试或 TS，不据此宣称通过。

[TableConsumer.vue](../../web/src/components/business/__tests__/TableConsumer.vue) 是 EntityTypeBrief / KnowledgeBase DTO、列 render、rowProps 与泛型 cell slot 的类型夹具。Chief 已同步该夹具；交付前读取确认使用 rows、v-model:selection 和 v-model:sort，旧 data / checked-row-keys 绑定已移除。此处是源码核对，不替代夹具的实际 TS 检查。

旧阶段的 19 项组件测试、临时 TS 通过和并行门面类型错误均属于当时快照，不作为本页当前结果。固定列、滚动、键盘、焦点、真实请求与整页交互的当前验证见[核验记录](../maintenance/verification-2026-11-26.md)。
