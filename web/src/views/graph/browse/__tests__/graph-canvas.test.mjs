import assert from 'node:assert/strict'
import { test } from 'node:test'

import { createRenderer } from 'vue'
import { createI18n } from 'vue-i18n'

import { compile, settle } from '../../../../testing/view-harness.mjs'

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
const graph = () => ({
  graph_revision_id: 1,
  run_id: 1,
  ontology_id: null,
  ontology_revision: null,
  nodes: ['a', 'b'].map((iri, index) => ({
    id: index + 1,
    iri,
    type_iri: 'Unit',
    row_key: iri,
    distance: index,
    attrs: { name: iri, size: 2 + index, date: `2024-01-0${index + 1}` },
  })),
  edges: [11, 12].map((id) => ({
    id,
    kind: 'DIRECT',
    subject: 'a',
    object_: 'b',
    predicate: 'rel',
    props: null,
    graph_revision_id: 1,
  })),
  type_counts: [],
  entity_total: 2,
  quarantine_count: 0,
  truncated: false,
})
async function setup(t, layoutId) {
  const oldDocument = globalThis.document
  globalThis.document = { addEventListener() {}, removeEventListener() {}, activeElement: null }
  const selections = []
  const edges = []
  const built = await compile(
    'views/graph/browse/components/GraphCanvas.vue',
    {},
    'camera,marks,positions,markPositions,drag,showLegend,showMinimap,scrollEl,startDrag,moveDrag,finishDrag,onCanvasKey,getContext,restoreContext,selectEdge,recordTabNavigation,onNodeFocus',
  )
  const app = renderer.createApp(
    { ...built.mod.default, render: () => null },
    {
      graph: graph(),
      neighborhood: false,
      layoutId,
      semanticContext: {
        config: { measure_property_iri: 'size', time_property_iri: 'date' },
        fields: [
          { iri: 'size', name: 'size', kind: 'PROPERTY', type_iri: 'Unit', datatype: 'integer' },
          { iri: 'date', name: 'date', kind: 'PROPERTY', type_iri: 'Unit', datatype: 'date' },
        ],
      },
      onSelect: (iri) => selections.push(iri),
      onSelectEdge: (edge, aggregate) => edges.push({ edge, aggregate }),
    },
  )
  app.use(
    createI18n({
      legacy: false,
      locale: 'en-US',
      messages: {},
      missingWarn: false,
      fallbackWarn: false,
    }),
  )
  const vm = app.mount({})
  await settle()
  const captured = new Set()
  vm.scrollEl = {
    setPointerCapture: (id) => captured.add(id),
    hasPointerCapture: (id) => captured.has(id),
    releasePointerCapture: (id) => captured.delete(id),
  }
  t.after(() => {
    app.unmount()
    built.cleanup()
    globalThis.document = oldDocument
  })
  return { vm, app, captured, selections, edges }
}
const pointer = (extra = {}) => ({
  button: 0,
  isPrimary: true,
  pointerId: 1,
  clientX: 100,
  clientY: 100,
  currentTarget: { focus() {} },
  ...extra,
})

for (const layout of ['sunburst', 'treemap', 'pack', 'gantt']) {
  test(`${layout} moves actual mark positions, restores snapshots and cancels without selecting`, async (t) => {
    const { vm, captured, selections } = await setup(t, layout)
    vm.camera = { x: 0, y: 0, scale: 0.5 }
    const mark = vm.marks.find((item) => item.iri)
    const original = vm.getContext()
    vm.startDrag(pointer(), mark.iri, mark.id)
    vm.moveDrag(pointer({ clientX: 103, clientY: 102 }))
    assert.deepEqual(vm.getContext(), original, 'movement below threshold is not a drag')
    vm.moveDrag(pointer({ clientX: 130, clientY: 120 }))
    const moved = vm.marks.find((item) => item.id === mark.id)
    assert.ok(Math.abs(moved.offsetX - 60) < 1e-9)
    assert.ok(Math.abs(moved.offsetY - 40) < 1e-9)
    assert.deepEqual(
      vm.positions,
      original.positions,
      'mark movement cannot write node coordinates',
    )
    vm.finishDrag(pointer())
    const saved = vm.getContext()
    assert.ok(
      Object.values(saved.markPositions).every(
        (point) => Number.isFinite(point.x) && Number.isFinite(point.y),
      ),
    )
    assert.equal(captured.size, 0)
    assert.deepEqual(selections, [], 'completed drag does not select')
    assert.equal(vm.restoreContext(original), true)
    assert.equal(vm.marks.find((item) => item.id === mark.id).offsetX, 0)
    assert.equal(vm.restoreContext(saved), true)
    for (const ending of ['pointercancel', 'lostpointercapture', 'Escape']) {
      const before = vm.getContext()
      vm.startDrag(pointer(), mark.iri, mark.id)
      vm.moveDrag(pointer({ clientX: 150, clientY: 130 }))
      if (ending === 'Escape')
        vm.onCanvasKey({ key: 'Escape', preventDefault() {}, stopPropagation() {} })
      else vm.finishDrag(pointer(), true)
      assert.deepEqual(vm.getContext(), before, `${ending} rolls back only the active gesture`)
      assert.equal(captured.size, 0)
    }
    assert.deepEqual(selections, [])
    const bad = structuredClone(saved)
    bad.markPositions[mark.id].x = NaN
    assert.equal(vm.restoreContext(bad), false)
    assert.deepEqual(vm.getContext(), saved, 'invalid snapshot is rejected atomically')
    const badPrevious = { ...saved, previousCamera: { x: Infinity, y: 0, scale: 1 } }
    assert.equal(vm.restoreContext(badPrevious), false)
  })
}

test('marks reject capture failure and nonfinite motion, retain click selection and discard old-owner cancellation', async (t) => {
  const { vm, app, selections } = await setup(t, 'pack')
  const mark = vm.marks.find((item) => item.iri)
  const original = vm.getContext()
  vm.scrollEl.setPointerCapture = () => {
    throw new Error('capture unavailable')
  }
  vm.startDrag(pointer(), mark.iri, mark.id)
  assert.equal(vm.drag, null)
  vm.scrollEl.setPointerCapture = () => {}
  vm.startDrag(pointer(), mark.iri, mark.id)
  vm.moveDrag(pointer({ clientX: NaN }))
  assert.deepEqual(vm.getContext(), original)
  vm.finishDrag(pointer())
  assert.deepEqual(selections, [mark.iri])
  vm.startDrag(pointer(), mark.iri, mark.id)
  vm.moveDrag(pointer({ clientX: 150 }))
  app._instance.props.graph = { ...graph(), graph_revision_id: 2 }
  await settle()
  assert.equal(vm.drag, null)
  assert.equal(vm.getContext().graphRevisionId, 2)
  assert.equal(vm.marks.find((item) => item.id === mark.id).offsetX, 0)
})

for (const layout of ['schema', 'sankey', 'chord', 'force']) {
  test(`${layout} emits explicit renderer identity without changing kind:id`, async (t) => {
    const { vm, edges } = await setup(t, layout)
    const selected = { ...graph().edges[0], subject: 'Unit', object_: 'Unit', props: { count: 2 } }
    vm.selectEdge(selected)
    assert.equal(edges[0].aggregate, layout !== 'force')
    assert.deepEqual(edges[0].edge, selected)
    assert.equal(`${edges[0].edge.kind}:${edges[0].edge.id}`, 'DIRECT:11')
  })
}

test('node focus restoration cannot reuse a consumed Tab or an earlier key gesture', async (t) => {
  const { vm } = await setup(t, 'force')
  const focus = []
  const previous = { classList: { contains: (name) => name === 'node' } }
  vm.scrollEl = {
    contains: (element) => element === previous,
    querySelectorAll: () =>
      ['a', 'b'].map((iri) => ({
        dataset: { iri },
        focus: () => focus.push(iri),
      })),
  }
  for (const shiftKey of [false, true]) {
    vm.recordTabNavigation({ key: 'Tab', shiftKey })
    vm.onNodeFocus({ relatedTarget: previous })
    // SVG paint reordering momentarily removes browser focus; restoring it
    // before the timeout queue runs must keep the selected logical node.
    vm.onNodeFocus({ relatedTarget: null })
    assert.deepEqual(focus, [])
    vm.recordTabNavigation({ key: 'Tab', shiftKey })
    vm.recordTabNavigation({ key: 'Enter' })
    vm.onNodeFocus({ relatedTarget: null })
    assert.deepEqual(focus, [])
  }
})
