import assert from 'node:assert/strict'
import { test } from 'node:test'

import { h, nextTick, ref } from 'vue'

import { control, load, render } from './controls-harness.mjs'

test('number parser keeps zero distinct from cleared and invalid values', async () => {
  const { parseNumberInput, formatDateInput, parseDateInput } = await load('inputTypes.ts')
  assert.equal(parseNumberInput('0'), 0)
  assert.equal(parseNumberInput(''), null)
  assert.equal(parseNumberInput('Infinity'), null)
  assert.equal(parseNumberInput('1.258', 0, 10, 2), 1.26)
  assert.equal(parseNumberInput('-2', 0), 0)
  const timestamp = new Date(2026, 0, 2, 3, 4, 5).getTime()
  assert.equal(parseDateInput(formatDateInput(timestamp, true)), timestamp)
  assert.equal(parseDateInput(''), null)
})

test('Select keeps numeric zero, string IDs and multi-selection distinct, and emits only changes', async (t) => {
  const events = []
  const options = [
    { value: 0, label: 'Zero' },
    { value: '0', label: 'String zero' },
  ]
  const ctx = await control('UiSelect.vue', {
    options,
    'onUpdate:value': (value, option) => events.push([value, option]),
  })
  t.after(ctx.stop)
  ctx.state.update(0)
  ctx.state.update(0)
  ctx.state.update('0')
  assert.deepEqual(events, [
    [0, options[0]],
    ['0', options[1]],
  ])
  await ctx.update({ multiple: true })
  ctx.state.update([0, '0'])
  ctx.state.update([0, '0'])
  ctx.state.clear()
  assert.deepEqual(events.slice(2), [
    [[0, '0'], options],
    [[], []],
  ])
})

test('remote Select passes search to its consumer and retains server options', async (t) => {
  const searches = []
  const options = [{ value: 7, label: 'Server result' }]
  const ctx = await control('UiSelect.vue', {
    options,
    filterable: true,
    remote: true,
    onSearch: (value) => searches.push(value),
  })
  t.after(ctx.stop)
  ctx.state.onSearch({ target: { value: 'unrelated query' } })
  ctx.state.onSearch({ target: { value: 'unrelated query' } })
  assert.deepEqual(searches, ['unrelated query'])
  assert.deepEqual(ctx.state.visibleOptions, options)
  await ctx.update({ remote: false })
  assert.deepEqual(ctx.state.visibleOptions, [])
})

test('Slider creates both range thumbs for null and commits the final primitive value', async (t) => {
  const events = []
  const ctx = await control('UiSlider.vue', {
    value: null,
    range: true,
    min: 10,
    max: 20,
    onChange: (value) => events.push(value),
  })
  t.after(ctx.stop)
  assert.deepEqual(ctx.state.values, [10, 20])
  ctx.state.commit([12, 18])
  assert.deepEqual(events, [[12, 18]])
})

test('text Input preserves numeric-looking strings and Boolean controls emit false', async (t) => {
  const text = []
  const input = await control('UiInput.vue', { 'onUpdate:value': (value) => text.push(value) })
  t.after(input.stop)
  input.state.update('001')
  input.state.update('001')
  input.state.update('')
  assert.deepEqual(text, ['001', ''])
  for (const entry of ['UiCheckbox.vue', 'UiSwitch.vue']) {
    const events = []
    const ctx = await control(entry, {
      [entry === 'UiCheckbox.vue' ? 'defaultChecked' : 'defaultValue']: true,
      [entry === 'UiCheckbox.vue' ? 'onUpdate:checked' : 'onUpdate:value']: (value) =>
        events.push(value),
    })
    t.after(ctx.stop)
    ctx.state.update(false)
    ctx.state.update(false)
    assert.deepEqual(events, [false])
  }
})

test('readonly and disabled controls reject updates', async (t) => {
  for (const entry of [
    'UiInput.vue',
    'UiInputNumber.vue',
    'UiSelect.vue',
    'UiCheckbox.vue',
    'UiSwitch.vue',
    'UiRadioGroup.vue',
    'UiSlider.vue',
  ]) {
    const events = []
    const ctx = await control(entry, {
      readonly: true,
      'onUpdate:value': (value) => events.push(value),
      'onUpdate:checked': (value) => events.push(value),
    })
    t.after(ctx.stop)
    ctx.state.update(
      entry === 'UiSlider.vue'
        ? [4]
        : entry === 'UiCheckbox.vue' || entry === 'UiSwitch.vue'
          ? true
          : '4',
    )
    assert.deepEqual(events, [], entry)
    await ctx.update({ readonly: false, disabled: true })
    ctx.state.update(
      entry === 'UiSlider.vue'
        ? [4]
        : entry === 'UiCheckbox.vue' || entry === 'UiSwitch.vue'
          ? true
          : '4',
    )
    assert.deepEqual(events, [], entry)
  }
})

test('Tree returns original ID types for select, expand and cascade checking', async (t) => {
  const events = { selected: [], expanded: [], checked: [] }
  const data = [{ key: 0, label: 'Parent', children: [{ key: '0', label: 'Child' }] }]
  const ctx = await control('UiTree.vue', {
    data,
    checkable: true,
    cascade: true,
    'onUpdate:selectedKeys': (keys) => events.selected.push(keys),
    'onUpdate:expandedKeys': (keys) => events.expanded.push(keys),
    'onUpdate:checkedKeys': (keys) => events.checked.push(keys),
  })
  t.after(ctx.stop)
  ctx.state.select({ preventDefault() {}, detail: { value: data[0] } })
  ctx.state.select({ preventDefault() {}, detail: { value: data[0] } })
  ctx.state.expand(['number:0'])
  ctx.state.check(data[0], true)
  ctx.state.check(data[0].children[0], false)
  assert.deepEqual(events.selected, [[0]])
  assert.deepEqual(events.expanded, [[0]])
  assert.deepEqual(events.checked, [[0, '0'], []])
})

test('Tree defaultExpandAll does not reopen a collapsed existing node after data refresh', async (t) => {
  const data = [{ key: 0, children: [{ key: 1 }] }]
  const ctx = await control('UiTree.vue', { data, defaultExpandAll: true })
  t.after(ctx.stop)
  assert.deepEqual(ctx.state.expanded, [0])
  ctx.state.expand([])
  await ctx.update({ data: [{ key: 0, children: [{ key: 1 }, { key: 2 }] }] })
  assert.deepEqual(ctx.state.expanded, [])
})

test('date range never retains a previously valid range when one endpoint is cleared', async (t) => {
  const events = []
  const ctx = await control('UiDatePicker.vue', {
    type: 'datetimerange',
    defaultValue: [new Date(2026, 0, 1).getTime(), new Date(2026, 0, 2).getTime()],
    'onUpdate:value': (value) => events.push(value),
  })
  t.after(ctx.stop)
  ctx.state.update('', 0)
  assert.deepEqual(events, [null])
  assert.notEqual(ctx.state.drafts[1], '')
  ctx.state.update('2026-01-03T00:00:00', 0)
  assert.deepEqual(events, [null])
  ctx.state.update('2026-01-01T00:00:00', 0)
  assert.deepEqual(events[1], [new Date(2026, 0, 1).getTime(), new Date(2026, 0, 2).getTime()])
  ctx.state.clear()
  assert.equal(events.at(-1), null)
})

test('rendered controls retain field names, input props and checked false semantics', async () => {
  const input = await render('UiInput.vue', {
    value: '001',
    inputProps: { 'aria-label': 'Record ID', autocomplete: 'off' },
  })
  assert.match(input, /value="001"/)
  assert.match(input, /aria-label="Record ID"/)
  assert.match(input, /autocomplete="off"/)
  assert.match(
    await render('UiCheckbox.vue', { checked: false, 'aria-label': 'Enabled' }),
    /aria-checked="false"/,
  )
  assert.match(await render('UiInputNumber.vue', { value: 0 }), /value="0"/)
})

test('date inputs keep explicit label targets and unique range endpoint IDs', async () => {
  const single = await render('UiDatePicker.vue', {
    inputProps: { id: 'published-at', 'aria-label': 'Published at' },
  })
  assert.match(single, /id="published-at"/)
  assert.match(single, /aria-label="Published at"/)
  const range = await render('UiDatePicker.vue', {
    type: 'daterange',
    id: 'period',
    'aria-label': 'Period',
  })
  assert.match(range, /id="period"/)
  assert.match(range, /id="period-1"/)
  assert.match(range, /aria-label="Period: Start"/)
  assert.match(range, /aria-label="Period: End"/)
})

test('controls receive field accessibility attributes and validate input and blur', async (t) => {
  const ctx = await control('UiInput.vue')
  t.after(ctx.stop)
  assert.equal(ctx.state.attributes.id, 'control-id')
  assert.equal(ctx.state.attributes['aria-labelledby'], 'control-label')
  assert.equal(ctx.state.attributes['aria-describedby'], 'control-help')
  assert.equal(ctx.state.attributes['aria-invalid'], true)
  ctx.state.update('value')
  ctx.state.blur({ type: 'blur' })
  assert.deepEqual(ctx.validation, ['input', 'blur'])
  const disabled = await control('UiSelect.vue', {}, { disabled: true })
  t.after(disabled.stop)
  assert.equal(disabled.state.disabled, true)
  disabled.state.update(3)
  assert.deepEqual(disabled.validation, [])
})

test('Tabs preserves numeric names and reacts to translated tab labels', async (t) => {
  const events = []
  const label = ref('Initial label')
  const slots = {
    default: () => [
      h('div', { name: 0, tab: label.value }),
      h('div', { name: '0', tab: 'Other label' }),
    ],
  }
  const ctx = await control(
    'UiTabs.vue',
    { 'onUpdate:value': (value) => events.push(value) },
    {},
    slots,
  )
  t.after(ctx.stop)
  assert.equal(ctx.state.value, 0)
  assert.equal(ctx.state.Label({ pane: ctx.state.panes[0] }), 'Initial label')
  label.value = 'Translated label'
  await nextTick()
  assert.equal(ctx.state.Label({ pane: ctx.state.panes[0] }), 'Translated label')
  ctx.state.update('string:0')
  assert.deepEqual(events, ['0'])
})

test('all facade templates compile against their actual imported primitives', async () => {
  for (const name of [
    'UiInput',
    'UiInputNumber',
    'UiSelect',
    'UiCheckbox',
    'UiSwitch',
    'UiRadioGroup',
    'UiRadioButton',
    'UiTabs',
    'UiTabPane',
    'UiSlider',
    'UiDatePicker',
    'UiTree',
    'UiCollapse',
    'UiCollapseItem',
  ]) {
    assert.equal(typeof (await load(`${name}.vue`, true)), 'object', name)
  }
})
