import assert from 'node:assert/strict'
import { before, test } from 'node:test'

import { h } from 'vue'

import { component, dispatch, find, mount, text } from './table-harness.mjs'

let Table, Pagination, Search, SearchTable, RowActions
before(async () => {
  ;[Table, Pagination, Search, SearchTable, RowActions] = await Promise.all([
    component('components/ui/UiDataTable.vue'),
    component('components/ui/UiPagination.vue'),
    component('components/business/SearchPanel.vue'),
    component('components/business/SearchTable.vue'),
    component('components/business/RowActions.vue'),
  ])
})
const columns = [
  { key: 'name', title: 'Entity name', sorter: true },
  { key: 'iri', title: 'IRI', minWidth: 300, ellipsis: { tooltip: true } },
]
const rows = Array.from({ length: 23 }, (_, i) => ({
  id: i + 1,
  name: `Type ${i + 1}`,
  iri: `https://example.org/${i + 1}`,
}))
const bodyRows = (tree) =>
  find(tree, (n) => n.type === 'tr' && n.props['data-row-key'] !== undefined)
const buttons = (tree) => find(tree, (n) => n.type === 'button')

test('remote page rows are never sliced, sorted, or filtered again; zero total is exact', async (t) => {
  const ctx = await mount(Table, {
    rows: rows.slice(20),
    columns,
    rowKey: (r) => r.id,
    mode: 'remote',
    total: 0,
    page: 3,
    pageSize: 20,
    sort: { columnKey: 'name', order: 'descend' },
    filters: { name: 'missing' },
  })
  t.after(ctx.stop)
  assert.equal(bodyRows(ctx.tree).length, 3)
  assert.deepEqual(
    bodyRows(ctx.tree).map((r) => r.props['data-row-key']),
    ['21', '22', '23'],
  )
  assert.equal(
    text(find(ctx.tree, (n) => n.props['data-testid'] === 'pagination-total')[0]),
    '0 items',
  )
  await ctx.update({ total: undefined })
  assert.equal(find(ctx.tree, (n) => n.props['data-testid'] === 'pagination-total').length, 0)
})

test('local complete collections clamp boundaries and pagination config notifies the consumer', async (t) => {
  const changes = []
  const updates = []
  const ctx = await mount(Table, {
    rows,
    columns,
    rowKey: 'id',
    mode: 'local',
    pagination: {
      page: 99,
      pageSize: 20,
      onChange: (page) => changes.push(page),
    },
    'onUpdate:page': (page) => updates.push(page),
  })
  t.after(ctx.stop)
  assert.equal(bodyRows(ctx.tree).length, 3)
  assert.deepEqual(updates, [2])
  assert.deepEqual(changes, [2])
  await dispatch(
    buttons(ctx.tree).find((b) => text(b) === 'Previous'),
    'onClick',
  )
  assert.equal(changes.at(-1), 1)
  // Controlled config does not silently mutate when its owner ignores an update.
  assert.equal(bodyRows(ctx.tree)[0].props['data-row-key'], '21')
  await ctx.update({ page: 1 })
  assert.equal(bodyRows(ctx.tree).length, 20)
  await ctx.update({ rows: [], total: 1000 })
  assert.equal(bodyRows(ctx.tree).length, 0)
  assert.equal(
    text(find(ctx.tree, (n) => n.props['data-testid'] === 'pagination-total')[0]),
    '0 items',
  )
  assert.equal(updates.at(-1), 1)
})

test('none is the safe default; data alias cannot override explicitly empty rows', async (t) => {
  const ctx = await mount(Table, { rows, columns, pagination: { page: 2, pageSize: 1 } })
  t.after(ctx.stop)
  assert.equal(bodyRows(ctx.tree).length, 23)
  assert.equal(find(ctx.tree, (n) => n.type === 'nav').length, 0)
  await ctx.update({ rows: [] })
  assert.equal(bodyRows(ctx.tree).length, 0)
})

test('sort is controlled and rendering follows the owner update without changing source data', async (t) => {
  const source = [
    { id: 1, name: 'Zeta' },
    { id: 2, name: 'Alpha' },
  ]
  const updates = []
  const ctx = await mount(Table, {
    rows: source,
    columns: [columns[0]],
    mode: 'local',
    pagination: false,
    'onUpdate:sort': (value) => updates.push(value),
  })
  t.after(ctx.stop)
  await dispatch(
    buttons(ctx.tree).find((b) => text(b) === 'Entity name'),
    'onClick',
  )
  assert.deepEqual(updates, [{ columnKey: 'name', order: 'ascend' }])
  assert.equal(bodyRows(ctx.tree)[0].props['data-row-key'], '1')
  await ctx.update({ sort: updates[0] })
  assert.equal(bodyRows(ctx.tree)[0].props['data-row-key'], '2')
  assert.equal(find(ctx.tree, (n) => n.type === 'th')[0].props['aria-sort'], 'ascending')
  assert.deepEqual(
    source.map((r) => r.id),
    [1, 2],
  )
})

test('selection preserves typed cross-page keys and row identity after sorting', async (t) => {
  const updates = []
  const checked = []
  const source = [
    { id: 1, name: 'Zeta' },
    { id: '1', name: 'Alpha' },
  ]
  const ctx = await mount(Table, {
    rows: source,
    columns: [{ type: 'selection' }, columns[0]],
    rowKey: 'id',
    mode: 'remote',
    total: 40,
    selection: ['other-page', 1],
    'onUpdate:selection': (...args) => {
      updates.push(args[0])
      checked.push(args)
    },
  })
  t.after(ctx.stop)
  const checkboxes = () => find(ctx.tree, (n) => n.type === 'input' && n.props.type === 'checkbox')
  assert.equal(checkboxes()[0].props['aria-checked'], 'mixed')
  assert.equal(checkboxes()[1].props.checked, true)
  assert.equal(checkboxes()[2].props.checked, false)
  await ctx.update({ loading: true })
  assert.equal(checkboxes()[0].props['aria-checked'], 'mixed')
  assert.equal(checkboxes()[1].props.checked, true)
  assert.equal(checkboxes()[1].props.disabled, true)
  await ctx.update({ loading: false })
  await dispatch(checkboxes()[2], 'onChange', { target: { checked: true } })
  assert.deepEqual(updates[0], ['other-page', 1, '1'])
  assert.deepEqual(
    checked[0][1].map((r) => r.id),
    [1, '1'],
  )
  assert.equal(checkboxes()[2].props.checked, false)
  await ctx.update({ selection: updates[0], rows: [source[1], source[0]] })
  assert.equal(checkboxes()[2].props.checked, true)
  await dispatch(checkboxes()[0], 'onChange', { target: { checked: false } })
  assert.deepEqual(updates.at(-1), ['other-page'])
  await ctx.update({ selection: [] })
  assert.equal(checkboxes()[1].props.checked, false)
})

test('cell slots and render callbacks consume typed rows; rowProps and keyboard events remain usable', async (t) => {
  const clicked = []
  const native = []
  const ctx = await mount(
    Table,
    {
      rows: [rows[0]],
      columns: [
        ...columns,
        {
          key: 'actions',
          title: 'Actions',
          width: 100,
          fixed: 'right',
          render: (r) => h('button', { type: 'button' }, `View ${r.id}`),
        },
      ],
      rowProps: (r) => ({ 'aria-label': r.name, onClick: () => native.push('click') }),
      onRowClick: (r) => clicked.push(r.id),
      scrollX: 800,
      maxHeight: 300,
    },
    { 'cell-name': ({ row }) => h('strong', {}, row.name) },
  )
  t.after(ctx.stop)
  assert.equal(text(find(ctx.tree, (n) => n.type === 'strong')[0]), 'Type 1')
  assert.equal(text(buttons(ctx.tree).find((b) => text(b) === 'View 1')), 'View 1')
  const row = bodyRows(ctx.tree)[0]
  assert.equal(row.props['aria-label'], 'Type 1')
  await dispatch(row, 'onClick')
  assert.deepEqual(native, ['click'])
  assert.deepEqual(clicked, [1])
  await dispatch(row, 'onKeydown', { key: 'Enter' })
  assert.deepEqual(clicked, [1, 1])
  await dispatch(row, 'onClick', { target: { closest: () => ({ tagName: 'BUTTON' }) } })
  assert.deepEqual(clicked, [1, 1])
  const cells = find(ctx.tree, (n) => n.type === 'td')
  assert.equal(cells.at(-1).props.style.position, 'sticky')
  assert.equal(cells.at(-1).props.style.right, '0px')
  assert.equal(find(ctx.tree, (n) => n.props.role === 'region')[0].props.style.maxHeight, '300px')
})

test('initial loading, refresh, initial query, empty, and errors have distinct rendered outcomes', async (t) => {
  const retries = []
  const ctx = await mount(
    Table,
    { rows: [], columns, initialized: false, onRetry: () => retries.push(1) },
    {
      initial: () => h('p', {}, 'Start a query'),
      refreshing: () => h('p', {}, 'Refreshing current rows'),
    },
  )
  t.after(ctx.stop)
  assert.match(text(ctx.tree), /Start a query/)
  await ctx.update({ loading: true })
  assert.doesNotMatch(text(ctx.tree), /Start a query|No data/)
  assert.equal(find(ctx.tree, (n) => n.props.role === 'status').length, 1)
  await ctx.update({ rows: [rows[0]] })
  assert.match(text(ctx.tree), /Refreshing current rows/)
  assert.equal(bodyRows(ctx.tree).length, 1)
  await ctx.update({ loading: false, rows: [], initialized: true, error: 'Conflict' })
  assert.doesNotMatch(text(ctx.tree), /No data/)
  assert.equal(text(find(ctx.tree, (n) => n.props.role === 'alert')[0]).includes('Conflict'), true)
  await dispatch(
    buttons(ctx.tree).find((b) => text(b) === 'Retry'),
    'onClick',
  )
  assert.deepEqual(retries, [1])
  await ctx.update({ error: null })
  assert.match(text(ctx.tree), /No data/)
})

test('remote count stays unknown while pending or failed and preserves the requested page', async (t) => {
  const updates = []
  const ctx = await mount(SearchTable, {
    rows: [],
    columns,
    searchable: false,
    mode: 'remote',
    page: 2,
    pageSize: 20,
    total: 0,
    loading: true,
    'onUpdate:page': (page) => updates.push(page),
  })
  t.after(ctx.stop)
  assert.doesNotMatch(text(ctx.tree), /0 items/)
  assert.match(text(ctx.tree), /Page 2/)
  assert.equal(find(ctx.tree, (n) => n.props['data-testid'] === 'pagination-total').length, 0)
  await ctx.update({ loading: false, error: 'Unavailable' })
  assert.doesNotMatch(text(ctx.tree), /0 items/)
  assert.deepEqual(updates, [])
  await ctx.update({ error: null, rows: rows.slice(20), total: 23 })
  assert.match(text(ctx.tree), /23 items/)
  assert.equal(bodyRows(ctx.tree).length, 3)
  await ctx.update({ page: 1, rows: [], total: 0 })
  assert.match(text(ctx.tree), /0 items/)
})

test('search Enter/form submit, clear and reset are explicit events and filters remain controlled', async (t) => {
  const submitted = []
  const queries = []
  const cleared = []
  const reset = []
  const expanded = []
  const ctx = await mount(
    Search,
    {
      query: '  employee  ',
      filters: { status: 'DRAFT' },
      onSubmit: (...args) => submitted.push(args),
      'onUpdate:query': (q) => queries.push(q),
      onClear: () => cleared.push(1),
      onReset: () => reset.push(1),
      'onUpdate:expanded': (v) => expanded.push(v),
    },
    { advanced: () => h('span', {}, 'Advanced filters') },
  )
  t.after(ctx.stop)
  const form = find(ctx.tree, (n) => n.type === 'form')[0]
  const input = find(ctx.tree, (n) => n.type === 'input')[0]
  assert.equal(find(ctx.tree, (n) => n.type === 'label')[0].props.for, input.props.id)
  await dispatch(form, 'onSubmit')
  assert.deepEqual(submitted, [['employee', { status: 'DRAFT' }]])
  await dispatch(input, 'onInput', { target: { value: 'next' } })
  assert.deepEqual(queries, ['next'])
  assert.equal(input.props.value, '  employee  ')
  await dispatch(
    buttons(ctx.tree).find(
      (b) => b.props.type === 'button' && b.props['aria-expanded'] === undefined,
    ),
    'onClick',
  )
  assert.equal(queries.at(-1), '')
  assert.equal(cleared.length, 1)
  assert.equal(submitted.length, 1)
  await dispatch(form, 'onReset')
  assert.equal(reset.length, 1)
  await dispatch(
    buttons(ctx.tree).find((b) => b.props['aria-expanded'] !== undefined),
    'onClick',
  )
  assert.deepEqual(expanded, [true])
  await ctx.update({ loading: true, query: 'second' })
  assert.equal(input.props.disabled, false)
  await dispatch(input, 'onInput', { target: { value: 'third' } })
  assert.equal(queries.at(-1), 'third')
  await dispatch(form, 'onSubmit')
  assert.equal(submitted.length, 2)
  assert.deepEqual(submitted.at(-1), ['second', { status: 'DRAFT' }])
  await ctx.update({ disabled: true })
  await dispatch(form, 'onSubmit')
  await dispatch(input, 'onInput', { target: { value: 'blocked' } })
  assert.equal(submitted.length, 2)
  assert.equal(queries.at(-1), 'third')
})

test('SearchTable forwards real page/selection/cell/search contracts and toolbar actions', async (t) => {
  const queries = []
  const pages = []
  const ctx = await mount(
    SearchTable,
    {
      query: 'types',
      rows: [rows[0]],
      columns,
      rowKey: 'id',
      mode: 'remote',
      total: 41,
      page: 1,
      pageSize: 20,
      onSubmit: (q) => queries.push(q),
      'onUpdate:page': (p) => pages.push(p),
    },
    {
      'cell-name': ({ row }) => h('strong', {}, row.name),
      'toolbar-actions': () => h('button', { type: 'button' }, 'Create type'),
    },
  )
  t.after(ctx.stop)
  assert.equal(text(find(ctx.tree, (n) => n.type === 'strong')[0]), 'Type 1')
  assert.match(text(ctx.tree), /41 items|Create type/)
  await dispatch(find(ctx.tree, (n) => n.type === 'form')[0], 'onSubmit')
  assert.deepEqual(queries, ['types'])
  await dispatch(
    buttons(ctx.tree).find((b) => text(b) === 'Next'),
    'onClick',
  )
  assert.deepEqual(pages, [2])
  assert.equal(bodyRows(ctx.tree).length, 1)
})

test('pagination zero total disables navigation, size events do not mutate controlled page', async (t) => {
  const sizes = []
  const ctx = await mount(Pagination, {
    page: 1,
    total: 0,
    pageSize: 20,
    showSizePicker: true,
    'onUpdate:pageSize': (n) => sizes.push(n),
  })
  t.after(ctx.stop)
  assert.equal(
    buttons(ctx.tree).every((b) => b.props.disabled),
    true,
  )
  assert.match(text(ctx.tree), /0 items/)
  await dispatch(find(ctx.tree, (n) => n.type === 'select')[0], 'onChange', {
    target: { value: '50' },
  })
  assert.deepEqual(sizes, [50])
  assert.match(text(ctx.tree), /Page 1/)
})

test('row actions preserve the business object and prevent disabled/destructive duplicate clicks', async (t) => {
  const calls = []
  const emitted = []
  const ctx = await mount(RowActions, {
    row: rows[0],
    actions: [
      { key: 'view', label: 'View', onClick: (r) => calls.push(r.id) },
      {
        key: 'delete',
        label: 'Delete',
        disabled: true,
        destructive: true,
        onClick: () => calls.push('bad'),
      },
    ],
    onAction: (key, row) => emitted.push([key, row.id]),
  })
  t.after(ctx.stop)
  await dispatch(buttons(ctx.tree)[0], 'onClick')
  await dispatch(buttons(ctx.tree)[1], 'onClick')
  assert.deepEqual(calls, [1])
  assert.deepEqual(emitted, [['view', 1]])
})

test('local filters preserve 0/false/null types and selection follows sorted business keys', async (t) => {
  const changes = []
  const filtered = []
  const source = [
    { id: 1, name: 'Zeta', status: 0 },
    { id: 2, name: 'Alpha', status: false },
    { id: 3, name: 'Beta', status: null },
  ]
  const ctx = await mount(Table, {
    rows: source,
    mode: 'local',
    rowKey: 'id',
    selection: [2],
    pagination: false,
    sort: { columnKey: 'name', order: 'ascend' },
    columns: [
      { type: 'selection' },
      columns[0],
      {
        key: 'status',
        title: 'Status',
        filter: true,
        filterOptions: [
          { label: 'Zero', value: 0 },
          { label: 'False', value: false },
          { label: 'Null', value: null },
        ],
      },
    ],
    'onUpdate:selection': (keys) => changes.push(keys),
    'onUpdate:filters': (value) => filtered.push(value),
  })
  t.after(ctx.stop)
  assert.equal(bodyRows(ctx.tree)[0].props['data-row-key'], '2')
  assert.equal(find(ctx.tree, (n) => n.type === 'input')[1].props.checked, true)
  await dispatch(find(ctx.tree, (n) => n.type === 'select')[0], 'onChange', {
    target: { value: '0' },
  })
  assert.deepEqual(filtered, [{ status: 0 }])
  assert.equal(bodyRows(ctx.tree).length, 3)
  await ctx.update({ filters: filtered[0] })
  assert.deepEqual(
    bodyRows(ctx.tree).map((r) => r.props['data-row-key']),
    ['1'],
  )
  await ctx.update({ filters: { status: false } })
  assert.deepEqual(
    bodyRows(ctx.tree).map((r) => r.props['data-row-key']),
    ['2'],
  )
  await ctx.update({ filters: { status: null } })
  assert.deepEqual(
    bodyRows(ctx.tree).map((r) => r.props['data-row-key']),
    ['3'],
  )
  assert.deepEqual(changes, [])
})

test('remote filter changes forward typed values without processing the current page', async (t) => {
  const changes = []
  const ctx = await mount(Table, {
    rows: rows.slice(20),
    rowKey: 'id',
    mode: 'remote',
    total: 23,
    page: 2,
    filters: { name: ['missing'] },
    columns: [
      {
        ...columns[0],
        filter: true,
        filterMultiple: true,
        filterOptions: [
          { label: 'Zero', value: 0 },
          { label: 'False', value: false },
        ],
      },
    ],
    'onUpdate:filters': (value) => changes.push(value),
  })
  t.after(ctx.stop)
  assert.equal(bodyRows(ctx.tree).length, 3)
  await dispatch(find(ctx.tree, (n) => n.type === 'select')[0], 'onChange', {
    target: { selectedOptions: [{ value: '0' }, { value: '1' }] },
  })
  assert.deepEqual(changes, [{ name: [0, false] }])
  assert.equal(bodyRows(ctx.tree).length, 3)
})

test('multiple sorter priority is honored and another column remains controlled', async (t) => {
  const changes = []
  const source = [
    { id: 1, name: 'Zeta', group: 1 },
    { id: 2, name: 'Alpha', group: 2 },
    { id: 3, name: 'Beta', group: 1 },
  ]
  const ctx = await mount(Table, {
    rows: source,
    mode: 'local',
    rowKey: 'id',
    pagination: false,
    columns: [
      {
        key: 'name',
        title: 'Name',
        sorter: { compare: (a, b) => a.name.localeCompare(b.name), multiple: 1 },
      },
      {
        key: 'group',
        title: 'Group',
        sorter: { compare: (a, b) => a.group - b.group, multiple: 2 },
      },
    ],
    sort: [
      { columnKey: 'name', order: 'ascend' },
      { columnKey: 'group', order: 'ascend' },
    ],
    'onUpdate:sort': (s) => changes.push(s),
  })
  t.after(ctx.stop)
  assert.deepEqual(
    bodyRows(ctx.tree).map((r) => r.props['data-row-key']),
    ['3', '1', '2'],
  )
  await dispatch(
    buttons(ctx.tree).find((b) => text(b) === 'Name'),
    'onClick',
  )
  assert.deepEqual(changes, [
    [
      { columnKey: 'group', order: 'ascend' },
      { columnKey: 'name', order: 'descend' },
    ],
  ])
  assert.deepEqual(
    bodyRows(ctx.tree).map((r) => r.props['data-row-key']),
    ['3', '1', '2'],
  )
})

test('unknown remote total preserves the requested page and never invents page count', async (t) => {
  const changes = []
  const ctx = await mount(
    Pagination,
    { page: 3, pageSize: 20, 'onUpdate:page': (p) => changes.push(p) },
    {
      default: ({ pageCount }) =>
        h(
          'span',
          { 'data-testid': 'known-pages' },
          pageCount === undefined ? 'Unknown' : String(pageCount),
        ),
    },
  )
  t.after(ctx.stop)
  assert.match(text(ctx.tree), /Page 3/)
  assert.equal(text(find(ctx.tree, (n) => n.props['data-testid'] === 'known-pages')[0]), 'Unknown')
  assert.equal(buttons(ctx.tree).find((b) => text(b) === 'Next').props.disabled, true)
  assert.deepEqual(changes, [])
  await dispatch(
    buttons(ctx.tree).find((b) => text(b) === 'Previous'),
    'onClick',
  )
  assert.deepEqual(changes, [2])
})

test('SearchTable forwards selection metadata, custom errors, retry and page callbacks', async (t) => {
  const selection = []
  const pages = []
  const retries = []
  const ctx = await mount(
    SearchTable,
    {
      searchable: false,
      rows: [rows[0]],
      columns: [{ type: 'selection' }, columns[0]],
      rowKey: 'id',
      mode: 'remote',
      total: 41,
      selection: [],
      pagination: { page: 1, pageSize: 20, onChange: (page) => pages.push(page) },
      'onUpdate:selection': (...args) => selection.push(args),
      onRetry: () => retries.push(1),
    },
    { error: ({ error, retry }) => h('button', { type: 'button', onClick: retry }, error) },
  )
  t.after(ctx.stop)
  await dispatch(find(ctx.tree, (n) => n.type === 'input')[1], 'onChange', {
    target: { checked: true },
  })
  assert.deepEqual(selection[0][0], [1])
  assert.equal(selection[0][1][0].id, 1)
  assert.equal(selection[0][2].action, 'check')
  await dispatch(
    buttons(ctx.tree).find((b) => text(b) === 'Next'),
    'onClick',
  )
  assert.deepEqual(pages, [2])
  await ctx.update({ error: 'Retry conflict' })
  await dispatch(
    buttons(ctx.tree).find((b) => text(b) === 'Retry conflict'),
    'onClick',
  )
  assert.deepEqual(retries, [1])
})

test('SearchTable remains editable while loading so the owner can replace an in-flight query', async (t) => {
  const submitted = []
  let active
  const ctx = await mount(SearchTable, {
    query: 'first',
    rows: [],
    columns,
    mode: 'remote',
    total: 0,
    'onUpdate:query': (query) => {
      ctx.props.query = query
    },
    onSubmit: (query) => {
      active?.abort()
      active = new AbortController()
      submitted.push({ query, signal: active.signal })
      ctx.props.loading = true
    },
  })
  t.after(ctx.stop)
  const form = find(ctx.tree, (n) => n.type === 'form')[0]
  await dispatch(form, 'onSubmit')
  assert.equal(form.props['aria-busy'], true)
  const input = find(ctx.tree, (n) => n.type === 'input')[0]
  assert.equal(input.props.disabled, false)
  const submit = buttons(ctx.tree).find((b) => b.props.type === 'submit')
  assert.equal(submit.props.disabled, false)
  await dispatch(input, 'onInput', { target: { value: 'second' } })
  await dispatch(form, 'onSubmit')
  assert.deepEqual(
    submitted.map((item) => item.query),
    ['first', 'second'],
  )
  assert.equal(submitted[0].signal.aborted, true)
  assert.equal(submitted[1].signal.aborted, false)
})

test('default numeric cells use Intl while string codes, IRIs and explicit raw numbers remain intact', async (t) => {
  for (const locale of ['en-US', 'zh-CN']) {
    const row = {
      id: 1,
      amount: 12345.67,
      code: '001234567',
      iri: 'https://example.org/12345.67',
      identifier: 12345.67,
    }
    const ctx = await mount(
      Table,
      {
        rows: [row],
        rowKey: 'id',
        columns: [
          { key: 'amount', title: 'Amount' },
          { key: 'code', title: 'Code' },
          { key: 'iri', title: 'IRI' },
          { key: 'identifier', title: 'Identifier', format: 'raw' },
        ],
      },
      {},
      locale,
    )
    t.after(ctx.stop)
    const cells = find(ctx.tree, (n) => n.type === 'td')
    assert.equal(text(cells[0]), new Intl.NumberFormat(locale).format(row.amount))
    assert.equal(text(cells[1]), row.code)
    assert.equal(text(cells[2]), row.iri)
    assert.equal(text(cells[3]), String(row.identifier))
  }
})

test('pagination and toolbar format quantities without changing the actual total or page values', async (t) => {
  const Toolbar = await component('components/business/TableToolbar.vue')
  const formatted = new Intl.NumberFormat('en-US').format(12345)
  const pages = []
  const ctx = await mount(
    Pagination,
    { total: 12345, page: 1234, pageSize: 1, 'onUpdate:page': (page) => pages.push(page) },
    { default: ({ page }) => h('span', { 'data-testid': 'raw-page' }, typeof page) },
  )
  t.after(ctx.stop)
  assert.match(text(ctx.tree), new RegExp(formatted))
  assert.match(text(ctx.tree), /Page 1,234/)
  await dispatch(
    buttons(ctx.tree).find((b) => text(b) === 'Next'),
    'onClick',
  )
  assert.deepEqual(pages, [1235])
  const toolbar = await mount(
    Toolbar,
    { total: 12345 },
    {
      summary: ({ total }) => h('span', { 'data-testid': 'raw-total' }, `${typeof total}:${total}`),
    },
  )
  t.after(toolbar.stop)
  assert.equal(
    text(find(toolbar.tree, (n) => n.props['data-testid'] === 'raw-total')[0]),
    'number:12345',
  )
  const defaults = await mount(Toolbar, { total: 12345 })
  t.after(defaults.stop)
  assert.match(text(defaults.tree), new RegExp(formatted))
})
