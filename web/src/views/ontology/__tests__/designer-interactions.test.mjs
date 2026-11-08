import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../__tests__/view-harness.mjs'
import { designerEdges } from '../components/designerGeometry.ts'

const resource = (id, name = `Type${id}`) => ({
  id,
  name,
  iri: `https://example.org/${name}`,
  label_i18n: { 'en-US': name },
  status: 'PUBLISHED',
  current_revision: 1,
  edit_revision: 3,
})
const snapshot = (id, kind = 'ENTITY', name = `Frozen${id}`) => ({
  resource_id: id,
  revision: 1,
  snapshot: {
    ...resource(id, name),
    kind,
    resource_refs: [],
    parent_ids: [],
    datatype_props: [{ name: 'frozenProperty', datatype: 'string' }],
  },
})

async function setup(t, extra = {}) {
  const writes = []
  const onto = {
    list: async () => [resource(1), resource(2)],
    get: async (id) => resource(id),
    refs: async () => [1, 2, 3].map((id) => ({ id, resource_id: id, pinned_revision: 1 })),
    getCanvas: async () => ({ positions: { 1: { x: 100, y: 100 }, 2: { x: 500, y: 100 } } }),
    saveCanvas: async (...args) => writes.push(['layout', ...args]),
    addRef: async (...args) => writes.push(['add', ...args]),
    removeRef: async (...args) => writes.push(['remove', ...args]),
    publish: async (...args) => writes.push(['publish', ...args]),
    update: async (...args) => writes.push(['update', ...args]),
    rules: async () => [{ rule_id: 1 }],
  }
  const frozen = [snapshot(1), snapshot(2), snapshot(3, 'OBJECT_PROP', 'FrozenRelation')]
  frozen[2].snapshot.resource_refs = [
    { role: 'relation_domain', target_id: 1 },
    { role: 'relation_range', target_id: 1 },
  ]
  const history = {
    contents: async () => ({
      resources: frozen.map((r) => ({ resource_id: r.resource_id, revision: 1 })),
      rules: [],
    }),
    resource: async (_onto, _revision, id) => frozen.find((r) => r.resource_id === id),
    ...extra.history,
  }
  const ctx = await mount(
    'views/ontology/Designer.vue',
    {
      '@/api/ontology': { ontologyApi: onto },
      '@/api/entity-types': {
        entityTypesApi: {
          list: async () => [resource(1, 'Current1'), resource(2, 'Current2')],
          get:
            extra.getType ??
            (async (id) => ({
              ...resource(id),
              data_props: [{ name: 'liveProperty', datatype: 'string' }],
            })),
        },
      },
      '@/api/relations': {
        relationsApi: {
          list: async () => [resource(3, 'CurrentRelation')],
          get: async () => ({
            ...resource(3),
            domain_spec: { type_id: 1 },
            range_spec: { type_id: 2 },
          }),
        },
      },
      '@/api/domains': { domainsApi: { list: async () => [] } },
      '@/api/governance': {
        rulesApi: { all: async () => [{ id: 1, identifier: 'rule', revision: 1 }] },
      },
      '@/api/ontology-history': { ontologyHistoryApi: history },
      '@/api/validation': {
        validationApi: {
          validateOntology: async () => {
            writes.push(['validation'])
            return { report_id: 1 }
          },
          getResults: async () =>
            ['PASS', 'VIOLATION', 'NA', 'NOT_RUN'].map((state, i) => ({
              check_code: `A0${i}`,
              state,
            })),
        },
      },
    },
    'auth,canEdit,nodes,edges,positions,pan,zoom,layoutDirty,savedPositions,saveError,selectedKey,inspectorOpen,canvasEl,onWheel,onNodeDown,onNodeMove,onNodeUp,onBackgroundDown,onCanvasKey,cancelLayout,autoLayout,persist,addToCanvas,publish,removeFromCanvas,runValidation,validationResults,selectOntology,changeRevision,frozenRevision,historyError,inspectedProperties,showDiscard,answerDiscard,ontologyId,typeDetail,typeDetailLoading,selectedRules,savedRules,openRules,closeRules,showRules',
  )
  t.after(ctx.stop)
  ctx.vm.auth.user = { role: extra.role ?? 'EDITOR' }
  await settle()
  return { ...ctx, writes, onto, history }
}

test('designer preserves parallel, reverse and self-loop identities with separated labels and clipped endpoints', () => {
  const positions = { 1: { x: 0, y: 100 }, 2: { x: 500, y: 100 } }
  const links = [
    { id: 1, source: 1, target: 2 },
    { id: 2, source: 1, target: 2 },
    { id: 3, source: 2, target: 1 },
    { id: 4, source: 1, target: 1 },
    { id: 5, source: 1, target: 1 },
  ]
  const edges = designerEdges(links, positions, 180, 76)
  assert.equal(edges.length, 5)
  assert.equal(new Set(edges.map((edge) => edge.d)).size, 5)
  assert.equal(new Set(edges.map((edge) => `${edge.lx}:${edge.ly}`)).size, 5)
  assert.deepEqual(edges, designerEdges([...links].reverse(), positions, 180, 76))
  assert.ok(edges[3].ly < 100 && edges[4].ly < edges[3].ly)
  assert.ok(!edges[0].d.startsWith('M90 138 '), 'line starts on card boundary')
})

test('designer ordinary wheel pans; modifier zoom stays anchored and does not change positions', async (t) => {
  const { vm } = await setup(t)
  vm.canvasEl = { getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 600 }) }
  vm.pan = { x: 20, y: 30 }
  vm.zoom = 1
  const original = JSON.stringify(vm.positions)
  const event = {
    preventDefault() {},
    deltaX: 10,
    deltaY: 30,
    deltaMode: 0,
    ctrlKey: false,
    metaKey: false,
    clientX: 200,
    clientY: 150,
  }
  vm.onWheel(event)
  assert.deepEqual(vm.pan, { x: 10, y: 0 })
  assert.equal(vm.zoom, 1)
  const point = { x: (200 - vm.pan.x) / vm.zoom, y: (150 - vm.pan.y) / vm.zoom }
  vm.onWheel({ ...event, ctrlKey: true })
  assert.ok(vm.zoom < 1)
  assert.ok(Math.abs(point.x * vm.zoom + vm.pan.x - 200) < 1e-9)
  assert.ok(Math.abs(point.y * vm.zoom + vm.pan.y - 150) < 1e-9)
  assert.equal(JSON.stringify(vm.positions), original)
})

test('designer working publication remains editable; VIEWER blocks every write while selection stays available', async (t) => {
  const { vm, writes } = await setup(t)
  assert.equal(vm.canEdit, true)
  vm.auth.user = { role: 'VIEWER' }
  assert.equal(vm.canEdit, false)
  await vm.persist()
  await vm.addToCanvas(2)
  await vm.removeFromCanvas(1)
  await vm.publish()
  await vm.runValidation()
  vm.onNodeDown('1', { button: 0, stopPropagation() {} })
  assert.equal(vm.selectedKey, '1')
  assert.equal(vm.inspectorOpen, true)
  assert.deepEqual(writes, [])
})

test('designer layout drafts cancel, survive failed writes and require confirmation before switching', async (t) => {
  const { vm, onto } = await setup(t)
  const original = JSON.stringify(vm.positions)
  vm.autoLayout()
  assert.equal(vm.layoutDirty, true)
  vm.cancelLayout()
  assert.equal(JSON.stringify(vm.positions), original)
  vm.autoLayout()
  onto.saveCanvas = async () => {
    throw new Error('offline')
  }
  await vm.persist()
  assert.equal(vm.layoutDirty, true)
  assert.ok(vm.saveError)
  const selection = vm.selectOntology(2)
  assert.equal(vm.showDiscard, true)
  assert.equal(vm.ontologyId, 1)
  vm.answerDiscard(false)
  await selection
  assert.equal(vm.ontologyId, 1)
  assert.equal(vm.layoutDirty, true)
  onto.saveCanvas = async () => {}
  await vm.persist()
  assert.equal(vm.layoutDirty, false)
  await vm.selectOntology(2)
  assert.equal(vm.ontologyId, 2)
})

test('designer refresh after assembly retains camera, existing positions and selection', async (t) => {
  const { vm } = await setup(t)
  vm.pan = { x: 35, y: -80 }
  vm.zoom = 0.77
  vm.selectedKey = '1'
  const previous = JSON.stringify(vm.positions)
  await vm.addToCanvas(2)
  assert.deepEqual(vm.pan, { x: 35, y: -80 })
  assert.equal(vm.zoom, 0.77)
  assert.equal(JSON.stringify(vm.positions), previous)
  assert.equal(vm.selectedKey, '1')
  vm.autoLayout()
  assert.equal(vm.layoutDirty, true)
  await vm.removeFromCanvas(3)
  assert.equal(vm.layoutDirty, true, 'semantic writes do not mark an unsaved layout as saved')
  vm.cancelLayout()
  assert.equal(JSON.stringify(vm.positions), previous)
})

test('designer frozen view reads historical names, endpoints and properties and restores working camera', async (t) => {
  const { vm, writes, history } = await setup(t)
  vm.pan = { x: 20, y: 30 }
  vm.zoom = 0.8
  vm.selectedKey = '1'
  await settle()
  assert.equal(vm.inspectedProperties[0].name, 'liveProperty')
  await vm.changeRevision(1)
  assert.equal(vm.canEdit, false)
  assert.equal(vm.nodes[0].label, 'Frozen1')
  assert.match(vm.edges[0].d, / C/)
  assert.equal(vm.edges[0].label, 'FrozenRelation')
  vm.selectedKey = '1'
  await settle()
  assert.equal(vm.inspectedProperties[0].name, 'frozenProperty')
  await vm.publish()
  await vm.persist()
  assert.deepEqual(writes, [])
  await vm.changeRevision(0)
  await settle()
  assert.equal(vm.selectedKey, '1')
  assert.equal(vm.inspectedProperties[0].name, 'liveProperty')
  assert.equal(vm.nodes[0].label, 'Current1')
  assert.deepEqual(vm.pan, { x: 20, y: 30 })
  assert.equal(vm.zoom, 0.8)
  history.resource = async () => {
    throw new Error('missing snapshot')
  }
  await vm.changeRevision(1)
  assert.ok(vm.historyError)
  assert.equal(vm.nodes.length, 0)
  assert.equal(vm.edges.length, 0)
})

test('designer cancels stale history and type detail reads without clearing the newer loading state', async (t) => {
  const old = deferred(),
    newer = deferred()
  const { vm, history } = await setup(t, {
    getType: (id) => (id === 1 ? old.promise : newer.promise),
  })
  vm.selectedKey = '1'
  await settle()
  vm.selectedKey = '2'
  await settle()
  old.resolve({ ...resource(1), data_props: [] })
  await settle()
  assert.equal(vm.typeDetailLoading, true)
  assert.equal(vm.typeDetail, null)
  newer.resolve({ ...resource(2), data_props: [] })
  await settle()
  assert.equal(vm.typeDetail.id, 2)
  assert.equal(vm.typeDetailLoading, false)
  const frozen = deferred()
  history.contents = () => frozen.promise
  const pending = vm.changeRevision(1)
  await settle()
  await vm.changeRevision(0)
  frozen.resolve({ resources: [], rules: [] })
  await pending
  assert.equal(vm.frozenRevision, null)
  assert.equal(vm.nodes[0].label, 'Current1')
})

test('designer rule cancellation restores saved selection and all four validation states remain distinct', async (t) => {
  const { vm } = await setup(t)
  await vm.openRules()
  vm.selectedRules = [2]
  const close = vm.closeRules()
  vm.answerDiscard(false)
  await close
  assert.equal(vm.showRules, true)
  assert.deepEqual(vm.selectedRules, [2])
  const discard = vm.closeRules()
  vm.answerDiscard(true)
  await discard
  assert.equal(vm.showRules, false)
  assert.deepEqual(vm.selectedRules, [1])
  await vm.runValidation()
  assert.deepEqual(
    vm.validationResults.map((item) => item.state),
    ['PASS', 'VIOLATION', 'NA', 'NOT_RUN'],
  )
})
