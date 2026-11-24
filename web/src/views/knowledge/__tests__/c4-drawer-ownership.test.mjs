import assert from 'node:assert/strict'
import { test } from 'node:test'

import { contents, deferred, find, mountDrawer, settle } from './c4-drawer-harness.mjs'

const document = (id = 'd1') => ({
  id,
  name: id,
  revision: 3,
  archived: false,
  latest_task: null,
  active_index: null,
  active_generation: 1,
  searchable: true,
  semantic_status: 'NOT_RUN',
})
const evidence = (chunk = 'c1', extra = {}) => ({
  hit: {
    chunk_id: chunk,
    kb_id: 1,
    kb_name: 'Example',
    document_id: 'd1',
    document_name: 'Example.txt',
    generation: 1,
    location: { start_offset: 0, end_offset: 4, start_line: 1, end_line: 1 },
    graph_links: [],
    section: 'example',
  },
  normalized_text: 'text evidence',
  parser_version: 'p1',
  chunker_version: 'c1',
  archived: false,
  historical: false,
  ...extra,
})
const graph = {
  revisions: async () => [{ id: 7 }],
  entities: async () => ({ items: [{ iri: 'urn:example:entity', row_key: 'example' }], total: 1 }),
  detail: async () => ({
    entity: { iri: 'urn:example:entity' },
    out_edges: [{ id: 9, predicate: 'urn:p', object_: 'urn:o' }],
  }),
}
async function openDraft(ctx) {
  const start = find(
    ctx.tree,
    (n) => n.type === 'button' && contents(n) === 'Add manual reference',
  )[0]
  assert.ok(start, 'production template exposes the open action')
  start.props.onClick()
  await settle()
  const form = ctx.vm.linkForm
  form.graph = 7
  await settle()
  form.entity = 'urn:example:entity'
  await settle()
  form.fact = 9
  const query = find(ctx.tree, (n) => n.type === 'input' && n.props.type === 'search')[0]
  assert.ok(query)
  query.props.onInput({ target: { value: 'unsent entity draft' } })
  await settle()
  assert.equal(form.canSave, true)
  return form
}
function fakeConfirm(t) {
  const original = Object.getOwnPropertyDescriptor(globalThis, 'window')
  const state = { accept: false, calls: 0 }
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      confirm() {
        state.calls++
        return state.accept
      },
      addEventListener() {},
      removeEventListener() {},
    },
  })
  t.after(() => {
    if (original) Object.defineProperty(globalThis, 'window', original)
    else delete globalThis.window
  })
  return state
}

for (const completion of ['success', 'failure']) {
  test(`document revoked ${completion} cannot refresh, emit, report errors or release a newer busy`, async (t) => {
    let reads = 0
    const writes = []
    const ctx = await mountDrawer(
      t,
      'DocumentDrawer.vue',
      {
        knowledge: {
          document: async (_kb, id) => {
            reads++
            return document(id)
          },
          tasks: async () => ({ items: [], total: 0 }),
          documentAction: (...args) => {
            const request = { ...deferred(), signal: args.at(-1) }
            writes.push(request)
            return request.promise
          },
        },
      },
      '?doc=d1',
    )
    const old = ctx.vm.act('archive')
    ctx.user.role = 'VIEWER'
    assert.equal(writes[0].signal.aborted, true)
    assert.equal(ctx.vm.busy, false)
    await ctx.vm.act('archive')
    assert.equal(writes.length, 1)
    ctx.user.role = 'EDITOR'
    const fresh = ctx.vm.act('archive')
    if (completion === 'success') writes[0].resolve(document())
    else writes[0].reject({ code: 'KG.INTERNAL_ERROR' })
    await old
    await settle()
    assert.equal(reads, 1)
    assert.equal(ctx.changed(), 0)
    assert.equal(ctx.vm.actionError, '')
    assert.equal(ctx.vm.busy, true)
    writes[1].resolve(document())
    await fresh
    await settle()
    assert.equal(ctx.changed(), 1)
    assert.equal(reads, 2)
    assert.equal(ctx.vm.busy, false)
  })
}

test('document action survives read refresh and token rotation but expires on user, session, object and unmount', async (t) => {
  const writes = []
  const reads = []
  let deferRead = false
  const ctx = await mountDrawer(
    t,
    'DocumentDrawer.vue',
    {
      knowledge: {
        document: async (_kb, id) => {
          if (!deferRead) return document(id)
          const request = deferred()
          reads.push(request)
          return request.promise
        },
        tasks: async () => ({ items: [], total: 0 }),
        documentAction: (...args) => {
          const request = { ...deferred(), signal: args.at(-1) }
          writes.push(request)
          return request.promise
        },
      },
    },
    '?doc=d1',
  )
  let pending = ctx.vm.act('archive')
  deferRead = true
  ctx.vm.reload()
  await settle()
  ctx.refreshTokens()
  assert.equal(ctx.vm.loading, true)
  assert.equal(writes[0].signal.aborted, false)
  assert.equal(ctx.vm.busy, true)
  reads[0].reject({ code: 'KG.INTERNAL_ERROR' })
  await settle()
  assert.equal(writes[0].signal.aborted, false)
  ctx.user.id = 2
  assert.equal(writes[0].signal.aborted, true)
  writes[0].resolve(document())
  await pending
  deferRead = false
  ctx.vm.reload()
  await settle()
  pending = ctx.vm.act('archive')
  ctx.rotateSession()
  assert.equal(writes[1].signal.aborted, true)
  writes[1].reject({ code: 'KG.INTERNAL_ERROR' })
  await pending
  ctx.user = { id: 2, role: 'EDITOR', status: 'ACTIVE', username: 'next-session' }
  pending = ctx.vm.act('archive')
  await ctx.router.push('/knowledge-bases/1?doc=d2')
  await settle()
  assert.equal(writes[2].signal.aborted, true)
  writes[2].resolve(document())
  await pending
  pending = ctx.vm.act('archive')
  ctx.stop()
  assert.equal(writes[3].signal.aborted, true)
  writes[3].resolve(document('d2'))
  await pending
  assert.equal(ctx.changed(), 0)
})

test('graph draft remains stable through user/session changes and same-identity read refresh does not invalidate its write', async (t) => {
  const writes = []
  const reads = []
  const ctx = await mountDrawer(t, 'EvidenceDrawer.vue', {
    graph,
    knowledge: {
      evidence: async () => {
        if (!reads.length) {
          reads.push(null)
          return evidence()
        }
        const read = deferred()
        reads.push(read)
        return read.promise
      },
      document: async () => document(),
      link: (...args) => {
        const request = { ...deferred(), signal: args.at(-1) }
        writes.push(request)
        return request.promise
      },
    },
  })
  const form = await openDraft(ctx)
  let pending = form.save()
  await settle()
  ctx.vm.reload()
  await settle()
  assert.equal(ctx.vm.linkForm, form)
  assert.equal(writes[0].signal.aborted, false)
  assert.equal(form.busy, true)
  reads[1].resolve(evidence())
  await settle()
  assert.equal(writes[0].signal.aborted, false)
  ctx.user.id = 2
  assert.equal(writes[0].signal.aborted, true)
  writes[0].resolve({})
  await pending
  assert.equal(form.open, true)
  pending = form.save()
  await settle()
  ctx.rotateSession()
  assert.equal(writes[1].signal.aborted, true)
  writes[1].reject({ code: 'KG.INTERNAL_ERROR' })
  await pending
  await settle()
  assert.equal(ctx.vm.linkForm, form)
  assert.equal(form.query, 'unsent entity draft')
  assert.equal(form.error, '')
  assert.equal(form.canSave, false)
})

test('actual evidence template keeps the same draft on revoke, restore and same-identity refresh success/failure', async (t) => {
  const reads = []
  let writes = 0
  const ctx = await mountDrawer(t, 'EvidenceDrawer.vue', {
    graph,
    knowledge: {
      evidence: async (_kb, chunk) => {
        if (!reads.length) {
          reads.push(null)
          return evidence(chunk)
        }
        const request = deferred()
        reads.push(request)
        return request.promise
      },
      document: async () => document(),
      link: async () => {
        writes++
        return {}
      },
    },
  })
  const form = await openDraft(ctx)
  const stable = () => {
    assert.equal(ctx.vm.linkForm, form, 'child component must not unmount/remount')
    assert.equal(form.open, true)
    assert.equal(form.query, 'unsent entity draft')
    assert.equal(form.graph, 7)
    assert.equal(form.entity, 'urn:example:entity')
    assert.equal(form.fact, 9)
    assert.equal(
      find(ctx.tree, (n) => n.type === 'input' && n.props.type === 'search')[0].props.value,
      'unsent entity draft',
    )
  }
  ctx.user.role = 'VIEWER'
  await settle()
  stable()
  await form.save()
  assert.equal(writes, 0)
  assert.equal(form.canSave, false)
  assert.ok(find(ctx.tree, (n) => n.type === 'select').every((n) => n.props.disabled))
  ctx.user.role = 'EDITOR'
  await settle()
  stable()
  assert.equal(form.canSave, true)
  for (const fail of [false, true]) {
    ctx.vm.reload()
    await settle()
    stable()
    assert.equal(form.canSave, false)
    await form.save()
    assert.equal(writes, 0)
    if (fail) reads.at(-1).reject({ code: 'KG.INTERNAL_ERROR' })
    else reads.at(-1).resolve(evidence())
    await settle()
    stable()
    assert.equal(form.canSave, !fail)
  }
  assert.notEqual(ctx.vm.error, '')
})

for (const completion of ['success', 'failure']) {
  test(`graph link revoked ${completion} cannot close the draft or release a newer save`, async (t) => {
    const writes = []
    let evidenceReads = 0
    const ctx = await mountDrawer(t, 'EvidenceDrawer.vue', {
      graph,
      knowledge: {
        evidence: async () => {
          evidenceReads++
          return evidence()
        },
        document: async () => document(),
        link: (...args) => {
          const request = { ...deferred(), signal: args.at(-1) }
          writes.push(request)
          return request.promise
        },
      },
    })
    const form = await openDraft(ctx)
    const old = form.save()
    await settle()
    ctx.user.role = 'VIEWER'
    await settle()
    assert.equal(writes[0].signal.aborted, true)
    assert.equal(ctx.vm.linkForm, form)
    assert.equal(form.busy, false)
    await form.save()
    assert.equal(writes.length, 1)
    ctx.user.role = 'EDITOR'
    await settle()
    const fresh = form.save()
    await settle()
    assert.equal(writes.length, 2)
    if (completion === 'success') writes[0].resolve({})
    else writes[0].reject({ code: 'KG.INTERNAL_ERROR' })
    await old
    await settle()
    assert.equal(form.open, true)
    assert.equal(form.query, 'unsent entity draft')
    assert.equal(form.error, '')
    assert.equal(form.busy, true)
    assert.equal(evidenceReads, 1)
    writes[1].resolve({})
    await fresh
    await settle()
    assert.equal(form.open, false)
    assert.equal(evidenceReads, 2)
  })
}

test('real router denies evidence switch and close after revoke; accepted discard mounts only the new identity', async (t) => {
  const requested = []
  const ctx = await mountDrawer(t, 'EvidenceDrawer.vue', {
    graph,
    knowledge: {
      evidence: async (_kb, chunk) => {
        requested.push(chunk)
        return evidence(chunk)
      },
      document: async () => document(),
    },
  })
  const form = await openDraft(ctx)
  const confirmation = fakeConfirm(t)
  ctx.user.role = 'VIEWER'
  await settle()
  await ctx.router.push('/knowledge-bases/1?evidence=c2')
  await settle()
  assert.equal(ctx.router.currentRoute.value.query.evidence, 'c1')
  assert.equal(ctx.vm.linkForm, form)
  assert.equal(form.query, 'unsent entity draft')
  assert.deepEqual(requested, ['c1'])
  ctx.vm.close()
  await settle()
  assert.equal(form.open, true)
  assert.equal(confirmation.calls, 2)
  confirmation.accept = true
  await ctx.router.push('/knowledge-bases/1?evidence=c2')
  await settle()
  assert.equal(form.$.isUnmounted, true)
  assert.notEqual(ctx.vm.linkForm, form)
  assert.equal(ctx.vm.linkForm.open, false)
  assert.equal(ctx.vm.linkForm.query, '')
  assert.deepEqual(requested, ['c1', 'c2'])
})

test('evidence archival keeps the mounted draft disabled and unmount invalidates a pending link', async (t) => {
  const write = deferred()
  let signal
  let archived = false
  const ctx = await mountDrawer(t, 'EvidenceDrawer.vue', {
    graph,
    knowledge: {
      evidence: async () => evidence('c1', { archived }),
      document: async () => document(),
      link: (...args) => {
        signal = args.at(-1)
        return write.promise
      },
    },
  })
  const form = await openDraft(ctx)
  ctx.props.baseArchived = true
  await settle()
  assert.equal(ctx.vm.linkForm, form)
  assert.equal(form.canSave, false)
  ctx.props.baseArchived = false
  archived = true
  ctx.vm.reload()
  await settle()
  assert.equal(ctx.vm.linkForm, form)
  assert.equal(form.query, 'unsent entity draft')
  assert.equal(form.canSave, false)
  archived = false
  ctx.vm.reload()
  await settle()
  const pending = form.save()
  await settle()
  ctx.stop()
  assert.equal(form.$.isUnmounted, true)
  assert.equal(signal.aborted, true)
  write.resolve({})
  await pending
})
