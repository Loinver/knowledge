import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { mkdir, readFile, unlink } from 'node:fs/promises'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'

import { compileScript, compileTemplate, parse } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { build } from 'esbuild'
import { createRenderer, createSSRApp, h, reactive, ref } from 'vue'
import { createI18n } from 'vue-i18n'

import { compile, deferred, root, settle } from '../../../../../testing/view-harness.mjs'

const entry = 'views/ontology/designer/components/AiSuggestions.vue'
const sourceFile = path.join(root, 'web/src', entry)
const messages = JSON.parse(await readFile(path.join(root, 'web/src/locales/en-US.json'), 'utf8'))
const translations = () =>
  createI18n({ legacy: false, locale: 'en-US', messages: { 'en-US': messages } })
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
const suggestion = (id, targetId = 1, payload = {}) => ({
  id,
  kind: 'ONTOLOGY_COMPLETION',
  target_id: targetId,
  title: `Suggestion ${id}`,
  explanation: '',
  status: 'PENDING',
  payload,
  created_at: '2026-11-20T00:00:00Z',
  resolved_at: null,
})

async function mountPanel(t, overrides = {}, initial = {}) {
  const api = {
    suggestCompletion: async (id) => [suggestion(id, id)],
    suggestMapping: async (id) => [suggestion(id, id)],
    extractDocument: async (id) => [suggestion(id, id)],
    apply: async (id) => suggestion(id),
    discard: async (id) => suggestion(id),
    ...overrides,
  }
  const built = await compile(
    entry,
    { '@/api/ai': { aiApi: api } },
    'items,loading,busyId,error,notice,loaded,generate,apply,discard',
  )
  const props = reactive({ kind: 'ONTOLOGY_COMPLETION', title: 'AI', targetId: 1, ...initial })
  const component = { ...built.mod.default, render: () => null }
  const panel = ref()
  const applied = []
  const i18n = translations()
  const app = renderer
    .createApp({
      // Run the real SFC setup and composable with real parent-to-child prop updates.
      render: () =>
        h(component, {
          ...props,
          ref: panel,
          onApplied: (id) => applied.push(id),
        }),
    })
    .use(i18n)
  app.mount({})
  const vm = panel.value
  let stopped = false
  const stop = () => {
    if (stopped) return
    app.unmount()
    built.cleanup()
    stopped = true
  }
  t.after(stop)
  return {
    vm,
    props,
    applied,
    stop,
    text: i18n.global.t,
    update: async (patch) => {
      Object.assign(props, patch)
      await settle()
    },
  }
}

for (const fail of [false, true]) {
  test(`target switch ignores old generate ${fail ? 'failure' : 'success'} and its loading cleanup`, async (t) => {
    const old = deferred()
    const current = deferred()
    const ctx = await mountPanel(t, {
      suggestCompletion: (id) => (id === 1 ? old.promise : current.promise),
    })
    const first = ctx.vm.generate()
    await ctx.update({ targetId: 2 })
    assert.deepEqual(ctx.vm.items, [])
    assert.equal(ctx.vm.loaded, false)
    const second = ctx.vm.generate()
    if (fail) old.reject({ code: 'KG.RESOURCE_NOT_FOUND' })
    else old.resolve([suggestion(1)])
    await first
    assert.equal(ctx.vm.loading, true)
    assert.equal(ctx.vm.error, '')
    assert.equal(ctx.vm.loaded, false)
    assert.deepEqual(ctx.vm.items, [])
    current.resolve([suggestion(2, 2)])
    await second
    assert.deepEqual(
      ctx.vm.items.map((item) => item.id),
      [2],
    )
    assert.equal(ctx.vm.loading, false)
  })

  test(`same-target generation ignores late ${fail ? 'failure' : 'success'} after latest result`, async (t) => {
    const old = deferred()
    const current = deferred()
    let calls = 0
    const ctx = await mountPanel(t, {
      suggestCompletion: () => (++calls === 1 ? old.promise : current.promise),
    })
    const first = ctx.vm.generate()
    const second = ctx.vm.generate()
    current.resolve([suggestion(20)])
    await second
    if (fail) old.reject({ code: 'KG.RESOURCE_NOT_FOUND' })
    else old.resolve([suggestion(10)])
    await first
    assert.deepEqual(
      ctx.vm.items.map((item) => item.id),
      [20],
    )
    assert.equal(ctx.vm.loaded, true)
    assert.equal(ctx.vm.loading, false)
    assert.equal(ctx.vm.error, '')
  })

  test(`returning to target A does not revive its earlier generate ${fail ? 'failure' : 'success'}`, async (t) => {
    const old = deferred()
    let calls = 0
    const ctx = await mountPanel(t, {
      suggestCompletion: async () => (++calls === 1 ? old.promise : [suggestion(30)]),
    })
    const first = ctx.vm.generate()
    await ctx.update({ targetId: 2 })
    await ctx.update({ targetId: 1 })
    await ctx.vm.generate()
    if (fail) old.reject({ code: 'KG.RESOURCE_NOT_FOUND' })
    else old.resolve([suggestion(10)])
    await first
    assert.deepEqual(
      ctx.vm.items.map((item) => item.id),
      [30],
    )
    assert.equal(ctx.vm.error, '')
  })
}

test('kind and datasource changes invalidate requests and use captured API arguments', async (t) => {
  const requests = []
  const request = (method, ...args) => {
    const pending = { method, args, ...deferred() }
    requests.push(pending)
    return pending.promise
  }
  const ctx = await mountPanel(t, {
    suggestCompletion: (...args) => request('completion', ...args),
    suggestMapping: (...args) => request('mapping', ...args),
    extractDocument: (...args) => request('document', ...args),
  })
  const first = ctx.vm.generate()
  await ctx.update({ kind: 'MAPPING_SUGGEST', datasourceId: 4 })
  const second = ctx.vm.generate()
  await ctx.update({ datasourceId: 5 })
  const third = ctx.vm.generate()
  await ctx.update({ kind: 'DOCUMENT_FACTS' })
  const fourth = ctx.vm.generate('Synthetic document')
  assert.deepEqual(
    requests.map(({ method, args }) => ({ method, args })),
    [
      { method: 'completion', args: [1] },
      { method: 'mapping', args: [1, 4] },
      { method: 'mapping', args: [1, 5] },
      { method: 'document', args: [1, 'Synthetic document'] },
    ],
  )
  requests[3].resolve([suggestion(40)])
  await fourth
  requests[0].resolve([suggestion(10)])
  requests[1].reject({ code: 'KG.RESOURCE_NOT_FOUND' })
  requests[2].resolve([suggestion(30)])
  await Promise.all([first, second, third])
  assert.deepEqual(
    ctx.vm.items.map((item) => item.id),
    [40],
  )
  assert.equal(ctx.vm.error, '')
})

for (const action of ['apply', 'discard']) {
  for (const fail of [false, true]) {
    test(`old ${action} ${fail ? 'failure' : 'success'} cannot affect a new target action`, async (t) => {
      const old = deferred()
      const current = deferred()
      const committed = []
      const ctx = await mountPanel(t, {
        [action]: async (id) => {
          await (id === 1 ? old.promise : current.promise)
          committed.push(id)
          return suggestion(id)
        },
      })
      await ctx.vm.generate()
      const first = ctx.vm[action](1)
      await ctx.update({ targetId: 2 })
      assert.equal(ctx.vm.busyId, null)
      assert.equal(ctx.vm.notice, '')
      assert.equal(ctx.vm.loaded, false)
      await ctx.vm.generate()
      const second = ctx.vm[action](2)
      if (fail) old.reject({ code: 'KG.REVISION_CONFLICT' })
      else old.resolve()
      await first
      assert.equal(ctx.vm.busyId, 2)
      assert.equal(ctx.vm.error, '')
      assert.equal(ctx.vm.notice, '')
      assert.deepEqual(ctx.applied, [])
      assert.deepEqual(
        ctx.vm.items.map((item) => item.id),
        [2],
      )
      // A successful old apply can still commit; invalidating UI is not a server rollback.
      assert.deepEqual(committed, fail ? [] : [1])
      current.resolve()
      await second
      assert.equal(ctx.vm.busyId, null)
      assert.deepEqual(ctx.vm.items, [])
      assert.deepEqual(ctx.applied, action === 'apply' ? [2] : [])
      assert.equal(ctx.vm.notice, action === 'apply' ? ctx.text('ai.applied') : '')
    })
  }

  test(`current ${action} failure keeps suggestions for retry`, async (t) => {
    let fail = true
    const ctx = await mountPanel(t, {
      [action]: async (id) => {
        if (fail) throw { code: 'KG.REVISION_CONFLICT' }
        return suggestion(id)
      },
    })
    await ctx.vm.generate()
    await ctx.vm[action](1)
    assert.ok(ctx.vm.error)
    assert.equal(ctx.vm.busyId, null)
    assert.deepEqual(
      ctx.vm.items.map((item) => item.id),
      [1],
    )
    assert.deepEqual(ctx.applied, [])
    fail = false
    await ctx.vm[action](1)
    assert.equal(ctx.vm.error, '')
    assert.deepEqual(ctx.vm.items, [])
    assert.deepEqual(ctx.applied, action === 'apply' ? [1] : [])
  })
}

test('duplicate actions and generate during a write do not start extra requests', async (t) => {
  const pending = deferred()
  const calls = []
  const ctx = await mountPanel(t, {
    suggestCompletion: async () => {
      calls.push('generate')
      return [suggestion(1), suggestion(2)]
    },
    apply: () => {
      calls.push('apply')
      return pending.promise
    },
    discard: async () => calls.push('discard'),
  })
  await ctx.vm.generate()
  const applying = ctx.vm.apply(1)
  await Promise.all([ctx.vm.apply(1), ctx.vm.apply(2), ctx.vm.discard(2), ctx.vm.generate()])
  assert.deepEqual(calls, ['generate', 'apply'])
  pending.resolve(suggestion(1))
  await applying
  assert.deepEqual(ctx.applied, [1])
  assert.deepEqual(
    ctx.vm.items.map((item) => item.id),
    [2],
  )
})

test('writes during generate, unknown IDs and review-only mode cannot call mutation APIs', async (t) => {
  const pending = deferred()
  const calls = []
  const ctx = await mountPanel(t, {
    suggestCompletion: () => pending.promise,
    apply: async (id) => calls.push(id),
    discard: async (id) => calls.push(id),
  })
  const generating = ctx.vm.generate()
  await Promise.all([ctx.vm.apply(1), ctx.vm.discard(1)])
  pending.resolve([suggestion(1)])
  await generating
  await Promise.all([ctx.vm.apply(99), ctx.vm.discard(99)])
  await ctx.update({ reviewOnly: true })
  await ctx.vm.generate()
  await Promise.all([ctx.vm.apply(1), ctx.vm.discard(1)])
  assert.deepEqual(calls, [])
})

test('generate failures, missing datasource and empty results preserve honest loaded state', async (t) => {
  let fail = true
  const ctx = await mountPanel(t, {
    suggestCompletion: async () => {
      if (fail) throw { code: 'KG.RESOURCE_NOT_FOUND' }
      return []
    },
  })
  await ctx.vm.generate()
  assert.ok(ctx.vm.error)
  assert.equal(ctx.vm.loading, false)
  assert.equal(ctx.vm.loaded, false)
  fail = false
  await ctx.vm.generate()
  assert.equal(ctx.vm.error, '')
  assert.equal(ctx.vm.loaded, true)
  assert.deepEqual(ctx.vm.items, [])
  await ctx.update({ kind: 'MAPPING_SUGGEST' })
  await ctx.vm.generate()
  assert.equal(ctx.vm.error, ctx.text('ai.datasourceRequired'))
  assert.equal(ctx.vm.loaded, false)
  assert.equal(ctx.vm.loading, false)
})

for (const operation of ['generate', 'apply', 'discard']) {
  for (const fail of [false, true]) {
    test(`unmount suppresses late ${operation} ${fail ? 'failure' : 'success'} and emitted refresh`, async (t) => {
      const pending = deferred()
      const calls = []
      const ctx = await mountPanel(t, {
        ...(operation === 'generate'
          ? {
              suggestCompletion: () => {
                calls.push('generate')
                return pending.promise
              },
            }
          : {
              [operation]: () => {
                calls.push(operation)
                return pending.promise
              },
            }),
      })
      if (operation !== 'generate') await ctx.vm.generate()
      const running = ctx.vm[operation](1)
      ctx.stop()
      if (fail) pending.reject({ code: 'KG.REVISION_CONFLICT' })
      else pending.resolve(operation === 'generate' ? [suggestion(1)] : suggestion(1))
      await running
      assert.deepEqual(ctx.vm.items, [])
      assert.equal(ctx.vm.loaded, false)
      assert.equal(ctx.vm.error, '')
      assert.equal(ctx.vm.notice, '')
      assert.equal(ctx.vm.loading, false)
      assert.equal(ctx.vm.busyId, null)
      assert.deepEqual(ctx.applied, [])
      await ctx.vm[operation](1)
      assert.deepEqual(calls, [operation])
    })
  }
}

test('production template renders nested model metadata and object arrays as escaped JSON', async () => {
  const payload = {
    resource_id: 8,
    label_i18n: { 'zh-CN': '示例', 'en-US': '<script>example</script>' },
    _model: {
      config_id: 3,
      config_revision: 7,
      default_revision: 2,
      model: 'example-model',
      model_version: 'v1',
    },
    entries: [{ name: 'Nested', values: [1, 2] }],
    scalar_list: ['A', 'B'],
    enabled: false,
    count: 0,
    absent: null,
    empty: '',
  }
  const id = `ai_render_${randomUUID().replaceAll('-', '')}`
  const outfile = path.join(root, 'web/node_modules/.tmp', `${id}.mjs`)
  globalThis[id] = [suggestion(1, 1, payload)]
  try {
    const source = (await readFile(sourceFile, 'utf8')).replace(
      '</script>',
      `items.value = globalThis[${JSON.stringify(id)}]; loaded.value = true\n</script>`,
    )
    const { descriptor } = parse(source, { filename: sourceFile })
    const script = compileScript(descriptor, {
      id,
      inlineTemplate: true,
      templateOptions: { ssr: true },
    })
    await mkdir(path.dirname(outfile), { recursive: true })
    await build({
      stdin: { contents: script.content, loader: 'ts', resolveDir: path.dirname(sourceFile) },
      outfile,
      bundle: true,
      platform: 'node',
      format: 'esm',
      packages: 'external',
      logLevel: 'silent',
      plugins: [
        {
          name: 'ai-render-offline',
          setup(b) {
            b.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
              const { descriptor } = parse(await readFile(filename, 'utf8'), { filename })
              if (!descriptor.script && !descriptor.scriptSetup) {
                const compiled = compileTemplate({
                  source: descriptor.template.content,
                  filename,
                  id,
                  ssr: true,
                  ssrCssVars: descriptor.cssVars,
                })
                assert.deepEqual(compiled.errors, [])
                return {
                  contents: `${compiled.code}\nexport default { ssrRender }`,
                  loader: 'ts',
                  resolveDir: path.dirname(filename),
                }
              }
              const compiled = compileScript(descriptor, {
                id,
                inlineTemplate: true,
                templateOptions: { ssr: true },
                fs: { fileExists: existsSync, readFile: (file) => readFileSync(file, 'utf8') },
              })
              return {
                contents: compiled.content,
                loader: 'ts',
                resolveDir: path.dirname(filename),
              }
            })
            b.onResolve({ filter: /^@\/api\/ai$/ }, () => ({ path: 'ai', namespace: 'stub' }))
            b.onLoad({ filter: /.*/, namespace: 'stub' }, () => ({
              contents: 'export const aiApi = {}',
            }))
            b.onResolve({ filter: /^@\// }, ({ path: p, kind, resolveDir }) =>
              b.resolve(path.join(root, 'web/src', p.slice(2)), { kind, resolveDir }),
            )
          },
        },
      ],
    })
    const component = (await import(pathToFileURL(outfile).href)).default
    const app = createSSRApp(component, { kind: 'ONTOLOGY_COMPLETION', title: 'AI', targetId: 1 })
    app.use(translations())
    const html = await renderToString(app)
    assert.doesNotMatch(html, /\[object Object\]/)
    assert.match(html, /_model:.*config_id.*3.*config_revision.*7.*example-model.*v1/)
    assert.match(html, /entries:.*Nested.*values/)
    assert.match(html, /scalar_list: A, B/)
    assert.match(html, /enabled: false/)
    assert.match(html, /count: 0/)
    assert.doesNotMatch(html, /absent:|empty:/)
    assert.match(html, /&lt;script&gt;example&lt;\/script&gt;/)
    assert.doesNotMatch(html, /<script>example<\/script>/)
    assert.deepEqual(globalThis[id][0].payload, payload)
  } finally {
    delete globalThis[id]
    await unlink(outfile).catch(() => {})
  }
})
