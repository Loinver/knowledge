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

test('fact navigation preserves the KB search context, graph pin and raw triple', async (t) => {
  const built = await compile('views/graph/components/GraphFactTable.vue', {}, 'columns')
  const row = Object.freeze({ id: 7, subject: 'A', predicate: 'WorksIn', object_: 'B' })
  const kbReturn = ref('/knowledge-bases/12/search?q=graph%20labels&source=7')
  const component = ref()
  const app = renderer.createApp({
    setup: () => () =>
      h(built.mod.default, {
        ref: component,
        items: [row],
        graphRevisionId: 9,
        relationLabels: { WorksIn: '任职于' },
        kbReturn: kbReturn.value,
      }),
  })
  app.use(createI18n({ legacy: false, locale: 'en-US', missingWarn: false, fallbackWarn: false }))
  app.mount({})
  t.after(() => {
    app.unmount()
    built.cleanup()
  })
  await settle()
  const destination = (key) =>
    component.value.columns.find((column) => column.key === key).render(row).props.to
  for (const key of ['subject', 'object_']) {
    assert.deepEqual(destination(key), {
      name: 'graph-entity-detail',
      params: { id: row[key] },
      query: { graph: 9, kbReturn: kbReturn.value },
    })
  }
  assert.deepEqual(destination('evidence'), {
    name: 'graph-evidence',
    query: { graph: 9, kbReturn: kbReturn.value, subject: 'A', predicate: 'WorksIn', object: 'B' },
  })
  kbReturn.value = undefined
  await settle()
  assert.equal(destination('evidence').query.kbReturn, undefined)
})
