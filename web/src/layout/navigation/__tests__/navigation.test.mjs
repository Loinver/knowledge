import assert from 'node:assert/strict'
import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'
import { test } from 'node:test'

import { compile, root } from '../../../testing/view-harness.mjs'
import { menuConfig, menuLeaves, menuTrail, visibleMenu } from '../menuConfig.ts'
import { routeIdentity } from '../routeIdentity.ts'
import { searchIndex } from '../searchIndex.ts'

const manifest = JSON.parse(
  await readFile(path.join(root, 'docs/frontend-migration-map-2026-11-21.json'), 'utf8'),
)
const locales = await Promise.all(
  ['zh-CN', 'en-US'].map(async (locale) =>
    JSON.parse(await readFile(path.join(root, `web/src/locales/${locale}.json`), 'utf8')),
  ),
)
const translate = (messages) => (key) =>
  key.split('.').reduce((value, part) => value?.[part], messages)
const built = await compile(
  'router/index.ts',
  {},
  '',
  (source) =>
    `${source.replaceAll('createWebHistory', 'createMemoryHistory')}\nexport { pinia, useAuthStore }\n`,
)
const { router, pinia, useAuthStore } = built.mod

test('all 41 existing URLs resolve to their original identity and actual migrated page', async () => {
  const routes = router.getRoutes().filter((route) => route.name)
  assert.equal(routes.length, 41)
  assert.deepEqual(routes.map((r) => r.name).sort(), manifest.routes.map((r) => r.name).sort())
  for (const route of routes) {
    const row = manifest.routes.find((item) => item.name === route.name)
    const source = await readFile(path.join(root, row.to), 'utf8')
    assert.match(row.to, /Page\.vue$/)
    assert.match(source, /<template>/)
    assert.ok(source.length > 500, `actual page implementation: ${row.to}`)
    assert.equal(route.meta.title, routeIdentity[route.name].title)
    for (const messages of locales)
      assert.equal(typeof translate(messages)(route.meta.title), 'string', route.name)
  }
  assert.equal(router.resolve('/graph/reports?graph=7#coverage').name, 'graph-reports')
  assert.equal(router.resolve('/extraction?mapping=23#review').name, 'mapping-wizard')
  const iri = 'https://example.org/person/甲?#part%encoded'
  const resolved = router.resolve({
    name: 'graph-entity-detail',
    params: { id: iri },
    query: { graph: '7', kbReturn: '/knowledge-bases/3?doc=8#hit' },
    hash: '#evidence',
  })
  const roundtrip = router.resolve(resolved.fullPath)
  assert.equal(roundtrip.params.id, iri)
  assert.deepEqual(roundtrip.query, resolved.query)
  assert.equal(roundtrip.hash, '#evidence')
})

test('target menu order, third level and hidden tools have one stable owner', () => {
  assert.deepEqual(
    menuConfig.map((node) => node.key),
    [
      'dashboard',
      'group:semantic-assets',
      'group:ontology',
      'group:data-integration',
      'group:graph',
      'group:governance',
      'knowledge-bases',
      'group:system',
    ],
  )
  assert.deepEqual(
    menuTrail('enum-dictionaries').map((node) => node.key),
    ['group:semantic-assets', 'group:configuration', 'enum-dictionaries'],
  )
  const leaves = menuLeaves()
  assert.equal(new Set(leaves.map((n) => n.key)).size, leaves.length)
  for (const leaf of leaves) assert.ok(router.hasRoute(leaf.key), leaf.key)
  for (const [name, owner] of Object.entries({
    'entity-detail': 'entity-types',
    'relation-detail': 'relation-types',
    'graph-entity-detail': 'graph-entities',
    'knowledge-base-detail': 'knowledge-bases',
    'knowledge-base-search': 'knowledge-bases',
    'sample-preview': 'data-catalog',
    'ai-assist': 'mapping-wizard',
  })) {
    assert.equal(routeIdentity[name].owner, owner)
    assert.ok(!leaves.some((leaf) => leaf.key === name))
  }
})

test('menu and search permissions include tools and account without indexing asset data', () => {
  const t = translate(locales[0])
  for (const isAdmin of [false, true]) {
    const entries = searchIndex(isAdmin, t)
    assert.equal(entries.filter((item) => item.key.startsWith('system-')).length, isAdmin ? 4 : 0)
    assert.equal(
      menuLeaves(visibleMenu(isAdmin)).filter((item) => item.key.startsWith('system-')).length,
      isAdmin ? 4 : 0,
    )
    for (const key of ['sample-preview', 'ai-assist', 'account-profile', 'account-security'])
      assert.ok(entries.some((item) => item.key === key))
    for (const entry of entries) assert.ok(router.hasRoute(entry.routeName))
  }
  assert.equal(searchIndex(false, t, '校验报告')[0]?.routeName, 'graph-reports')
  assert.equal(searchIndex(false, t, '实体类型详情')[0]?.routeName, 'entity-types')
})

test('route guard, menu and search derive ADMIN-only access from the navigation tree', () => {
  for (const route of router.getRoutes()) {
    if (!route.name) continue
    const expected = menuTrail(routeIdentity[route.name]?.owner ?? '').some(
      (node) => node.adminOnly,
    )
    assert.equal(Boolean(route.meta.adminOnly), expected, String(route.name))
  }
  assert.deepEqual(
    router
      .getRoutes()
      .filter((route) => route.meta.adminOnly)
      .map((route) => route.name)
      .sort(),
    ['system-ai-models', 'system-audit-logs', 'system-roles', 'system-users'],
  )
})

test('real guards retain login destination and reject every system page for EDITOR and VIEWER', async () => {
  const storage = new Map()
  const previousStorage = globalThis.localStorage
  globalThis.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  }
  const auth = useAuthStore(pinia)
  auth.user = null
  await router.push('/ontology/designer?ontology=42#selection')
  assert.equal(router.currentRoute.value.name, 'login')
  assert.equal(router.currentRoute.value.query.redirect, '/ontology/designer?ontology=42#selection')
  storage.set('kg-access-token', 'isolated-access')
  storage.set('kg-refresh-token', 'isolated-refresh')
  // Restore a fresh Pinia store after the login boundary so token presence is reevaluated.
  auth.$dispose()
  delete pinia.state.value.auth
  const signedIn = useAuthStore(pinia)
  for (const role of ['EDITOR', 'VIEWER', 'ADMIN']) {
    signedIn.user = { id: 99, username: 'isolated_actor', role, status: 'ACTIVE' }
    for (const name of ['system-users', 'system-roles', 'system-audit-logs', 'system-ai-models']) {
      await router.push({ name, query: { q: 'preserved' }, hash: '#section' })
      assert.equal(router.currentRoute.value.name, role === 'ADMIN' ? name : 'forbidden')
      if (role !== 'ADMIN')
        assert.match(router.currentRoute.value.query.redirect, /\?q=preserved#section$/)
    }
  }
  signedIn.$dispose()
  if (previousStorage === undefined) delete globalThis.localStorage
  else globalThis.localStorage = previousStorage
  built.cleanup()
})

test('production business imports do not cross another domain private implementation', async () => {
  async function files(dir) {
    return (
      await Promise.all(
        (await readdir(dir, { withFileTypes: true })).map((entry) =>
          entry.isDirectory() ? files(path.join(dir, entry.name)) : [path.join(dir, entry.name)],
        ),
      )
    ).flat()
  }
  const base = path.join(root, 'web/src/views')
  const violations = []
  for (const file of await files(base)) {
    if (!/\.(vue|ts)$/.test(file) || file.includes('__tests__')) continue
    const domain = path.relative(base, file).split(path.sep)[0]
    const source = await readFile(file, 'utf8')
    for (const match of source.matchAll(/(?:from\s*|import\s*\()['"]([^'"\n]+)['"]/g)) {
      const specifier = match[1]
      const resolved = specifier.startsWith('@/')
        ? path.join(root, 'web/src', specifier.slice(2))
        : specifier.startsWith('.')
          ? path.resolve(path.dirname(file), specifier)
          : ''
      if (
        resolved.startsWith(base + path.sep) &&
        path.relative(base, resolved).split(path.sep)[0] !== domain
      )
        violations.push(`${file}: ${specifier}`)
    }
  }
  assert.deepEqual(violations, [])
})
