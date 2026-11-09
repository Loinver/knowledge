import assert from 'node:assert/strict'
import { test } from 'node:test'

import { createRenderer, h, ref } from 'vue'
import { createI18n } from 'vue-i18n'

import { compile, settle } from '../../../__tests__/view-harness.mjs'

const renderer = createRenderer({
  createElement: () => ({}),
  createText: () => ({}),
  createComment: () => ({}),
  setText() {},
  setElementText() {},
  parentNode: () => null,
  nextSibling: () => null,
  insert() {},
  remove() {},
  patchProp() {},
})

test('evidence labels are presentation only: tooltip and every chain event preserve the original predicate', async (t) => {
  const built = await compile('views/graph/components/EvidenceTable.vue', {}, 'columns')
  const row = Object.freeze({ id: 7, subject: 'A', predicate: 'WorksIn', object: 'B' })
  const labels = ref({ WorksIn: '任职于' })
  const component = ref()
  const emitted = []
  const app = renderer.createApp({
    setup: () => () =>
      h(built.mod.default, {
        ref: component,
        items: [row],
        relationLabels: labels.value,
        onChain: (item) => emitted.push(item),
      }),
  })
  app.use(createI18n({ legacy: false, locale: 'en-US', missingWarn: false, fallbackWarn: false }))
  app.mount({})
  t.after(() => {
    app.unmount()
    built.cleanup()
  })
  await settle()
  const column = (key) => component.value.columns.find((entry) => entry.key === key)
  const translated = column('predicate').render(row)
  assert.equal(translated.children, '任职于')
  assert.equal(translated.props.title, 'WorksIn')
  assert.equal(translated.props['aria-label'], '任职于 · WorksIn')
  column('chain').render(row).props.onClick()

  labels.value = { WorksIn: 'WorksIn · Not translated' }
  await settle()
  assert.equal(column('predicate').render(row).children, 'WorksIn · Not translated')
  column('chain').render(row).props.onClick()

  labels.value = undefined
  await settle()
  assert.equal(column('predicate').render(row), 'WorksIn')
  column('chain').render(row).props.onClick()
  assert.equal(emitted.length, 3)
  assert.ok(emitted.every((item) => item === row))
  assert.equal(row.predicate, 'WorksIn')
})
