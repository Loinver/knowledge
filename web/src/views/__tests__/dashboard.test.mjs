import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { mkdir, readFile, unlink } from 'node:fs/promises'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { compileScript, parse } from '@vue/compiler-sfc'
import { build } from 'esbuild'
import { createRenderer, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'

const web = fileURLToPath(new URL('../../..', import.meta.url))
const empty = {
  entity_types: 0,
  relation_types: 0,
  domains: 0,
  ontologies: 0,
  datasources: 0,
  mappings: 0,
  runs: 0,
  current_graph_id: null,
  result_set_count: 0,
  quarantine_count: 0,
  unpublished_count: 0,
}
const populated = {
  entity_types: 57,
  relation_types: 58,
  domains: 59,
  ontologies: 60,
  datasources: 61,
  mappings: 205,
  runs: 64,
  current_graph_id: 18,
  result_set_count: 61,
  quarantine_count: 201,
  unpublished_count: 80,
}

const node = (type, text = '') => ({ type, text, props: {}, children: [], parent: null })
function remove(child) {
  if (child.parent) {
    child.parent.children.splice(child.parent.children.indexOf(child), 1)
    child.parent = null
  }
}
function insert(child, parent, anchor) {
  remove(child)
  child.parent = parent
  const index = anchor ? parent.children.indexOf(anchor) : -1
  if (index < 0) parent.children.push(child)
  else parent.children.splice(index, 0, child)
}

// Render the real template and composable, with lightweight UI-library hosts.
const renderer = createRenderer({
  createElement: (type) => node(type),
  createText: (text) => node('text', text),
  createComment: () => node('comment'),
  setText: (element, text) => (element.text = text),
  setElementText(element, text) {
    element.text = text
    element.children = []
  },
  parentNode: (element) => element.parent,
  nextSibling: (element) => {
    const siblings = element.parent?.children ?? []
    return siblings[siblings.indexOf(element) + 1] ?? null
  },
  insert,
  remove,
  patchProp: (element, key, _previous, value) => (element.props[key] = value),
  insertStaticContent(content, parent, anchor) {
    const element = node('static', content)
    insert(element, parent, anchor)
    return [element, element]
  },
})
const textContent = (element) => element.text + element.children.map(textContent).join('')
const find = (element, predicate) => [
  ...(predicate(element) ? [element] : []),
  ...element.children.flatMap((child) => find(child, predicate)),
]
const byClass = (root, name) =>
  find(root, (element) => element.props.class?.split(' ').includes(name))
const settle = async () => {
  await new Promise((resolve) => setImmediate(resolve))
  await nextTick()
}
function deferred() {
  let resolve
  let reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

async function mount(t, http, locale = 'en-US') {
  const key = `dashboard_${randomUUID()}`
  globalThis[key] = http
  const outfile = path.join(web, `node_modules/.tmp/${key}.mjs`)
  t.after(() => delete globalThis[key])
  await mkdir(path.dirname(outfile), { recursive: true })
  let component
  try {
    await build({
      entryPoints: [path.join(web, 'src/views/Dashboard.vue')],
      outfile,
      bundle: true,
      platform: 'node',
      format: 'esm',
      packages: 'external',
      logLevel: 'silent',
      plugins: [
        {
          name: 'dashboard-test',
          setup(bundler) {
            bundler.onResolve({ filter: /^@\/api\/client$/ }, ({ path }) => ({
              path,
              namespace: 'http-stub',
            }))
            bundler.onLoad({ filter: /.*/, namespace: 'http-stub' }, () => ({
              contents: `export const http = globalThis[${JSON.stringify(key)}]`,
            }))
            bundler.onResolve({ filter: /^(naive-ui|vue-router)$/ }, ({ path }) => ({
              path,
              namespace: 'ui-stub',
            }))
            bundler.onLoad({ filter: /.*/, namespace: 'ui-stub' }, () => ({
              resolveDir: web,
              contents: `
                import { h } from 'vue'
                export const NAlert = (props, {slots}) => h('aside', props, [props.title, slots.default?.()])
                export const NButton = (props, {slots}) => h('button', props, slots.default?.())
                export const NSpin = (props, {slots}) => h('div', props, slots.default?.())
                export const RouterLink = (props, {slots}) => h('a', {href: props.to.name}, slots.default?.())
              `,
            }))
            bundler.onResolve({ filter: /^@\// }, ({ path: module, kind, resolveDir }) =>
              bundler.resolve(path.join(web, 'src', module.slice(2)), { kind, resolveDir }),
            )
            bundler.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
              const { descriptor } = parse(await readFile(filename, 'utf8'), { filename })
              const script = compileScript(descriptor, { id: key, inlineTemplate: true })
              return { contents: script.content, loader: 'ts', resolveDir: path.dirname(filename) }
            })
          },
        },
      ],
    })
    component = (await import(pathToFileURL(outfile).href)).default
  } finally {
    await unlink(outfile).catch(() => {})
  }
  const messages = JSON.parse(await readFile(path.join(web, `src/locales/${locale}.json`), 'utf8'))
  const i18n = createI18n({ legacy: false, locale, messages: { [locale]: messages } })
  const root = node('root')
  const app = renderer.createApp(component).use(i18n)
  app.mount(root)
  let mounted = true
  const unmount = () => {
    if (mounted) app.unmount()
    mounted = false
  }
  t.after(unmount)
  return { root, i18n, unmount }
}

test('one cancellable aggregate request renders totals beyond the list page limits', async (t) => {
  const pending = deferred()
  const calls = []
  const { root, i18n } = await mount(t, {
    get: (...args) => {
      calls.push(args)
      return pending.promise
    },
  })
  assert.equal(calls.length, 1)
  assert.equal(calls[0][0], '/dashboard/stats')
  assert.ok(calls[0][1].signal instanceof AbortSignal)
  assert.equal(calls[0][1].signal.aborted, false)
  assert.ok(textContent(root).includes(i18n.global.t('common.loading')))
  assert.equal(byClass(root, 'pipe-count').length, 0)
  assert.equal(byClass(root, 'empty-ok').length, 0)

  pending.resolve({ data: populated })
  await settle()
  assert.equal(calls.length, 1)
  assert.deepEqual(byClass(root, 'pipe-count').map(textContent), [
    '57',
    '61',
    '205',
    '64',
    '61',
    '201',
  ])
  assert.deepEqual(byClass(root, 'asset-value').map(textContent), [
    '57',
    '58',
    '59',
    '60',
    '61',
    '64',
  ])
  assert.deepEqual(byClass(root, 'metric').map(textContent), ['61', '201'])
  assert.ok(textContent(root).includes(i18n.global.t('dashboard.resultSet', { id: 18 })))
  assert.ok(textContent(root).includes(i18n.global.t('dashboard.draftResources', { count: 80 })))
  assert.equal(byClass(root, 'loading-state').length, 0)
  assert.equal(byClass(root, 'empty-ok').length, 0)
})

for (const locale of ['zh-CN', 'en-US']) {
  test(`${locale}: errors do not display zero totals or healthy status; retry restores real empty state`, async (t) => {
    const requests = []
    const { root, i18n } = await mount(
      t,
      {
        get: (url, { signal }) => {
          assert.equal(url, '/dashboard/stats')
          const request = { signal, ...deferred() }
          requests.push(request)
          return request.promise
        },
      },
      locale,
    )
    requests[0].reject({ code: 'KG.SOURCE_UNREACHABLE' })
    await settle()
    assert.match(textContent(root), /KG.SOURCE_UNREACHABLE/)
    assert.equal(byClass(root, 'pipe-count').length, 0)
    assert.equal(byClass(root, 'metric').length, 0)
    assert.equal(byClass(root, 'empty-ok').length, 0)
    assert.equal(byClass(root, 'result-empty').length, 0)
    const retry = find(root, (element) => element.type === 'button')[0]
    assert.equal(textContent(retry), i18n.global.t('dashboard.retry'))
    assert.equal(i18n.global.te('dashboard.retry'), true)
    retry.props.onClick()
    await settle()
    assert.equal(requests.length, 2)
    assert.equal(requests[0].signal.aborted, true)
    assert.ok(textContent(root).includes(i18n.global.t('common.loading')))
    assert.doesNotMatch(textContent(root), /KG.SOURCE_UNREACHABLE/)

    requests[1].resolve({ data: empty })
    await settle()
    assert.deepEqual(byClass(root, 'metric').map(textContent), ['0', '0'])
    assert.ok(textContent(root).includes(i18n.global.t('dashboard.noIssues')))
    assert.ok(textContent(root).includes(i18n.global.t('dashboard.noCurrentGraph')))
    assert.doesNotMatch(textContent(root), /(?:dashboard|common)\.[A-Za-z]+/)
    if (locale === 'en-US') assert.doesNotMatch(textContent(root), /[\u4e00-\u9fff]/)
  })
}

test('leaving the dashboard cancels the request and ignores a late response', async (t) => {
  const pending = deferred()
  let signal
  const { root, unmount } = await mount(t, {
    get: (_url, options) => {
      signal = options.signal
      return pending.promise
    },
  })
  unmount()
  assert.equal(signal.aborted, true)
  pending.resolve({ data: populated })
  await settle()
  assert.equal(root.children.length, 0)
})
