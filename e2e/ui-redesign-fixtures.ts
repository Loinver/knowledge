import { randomUUID } from 'node:crypto'
import { copyFileSync, existsSync, realpathSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, join, resolve, sep } from 'node:path'

import { expect, test as base } from '@playwright/test'
import type {
  APIRequestContext,
  APIResponse,
  Page,
  Request,
  Response,
  Route,
  TestInfo,
} from '@playwright/test'

import { ADMIN, ensureAdmin } from './admin'

export const DESKTOP_VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
] as const

export type Role = 'ADMIN' | 'EDITOR' | 'VIEWER'
type Credentials = { account: string; password: string }
export type Resource = {
  id: number
  name: string
  iri: string
  status: string
  current_revision: number
  label_i18n: Record<string, string>
}
type EntityCatalog = {
  namespace: { id: number; prefix: string }
  draft: Resource
  published: Resource
}
export type RouteCatalog = EntityCatalog & {
  relation: Resource
  domain: Resource
  ontology: Resource
  datasourceId: number
  mappingId: number
  runId: number
  graphId: number
  entityIri: string
}
type Identity = { api: APIRequestContext; credentials: Record<Role, Credentials> }
type ApiTarget = { path: string; method?: string; query?: Record<string, string> }
type ApiObservation = { path: string; method: string; status: number }
type Injection = ApiTarget & { kind: 'empty' | 'failure' | 'delay'; hits: number }
type Evidence = {
  pending: Set<Request>
  responses: ApiObservation[]
  pageErrors: string[]
  failedRequests: string[]
  allowedFailures: ApiObservation[]
  injections: Injection[]
}
type Hold = { release: () => void; hits: () => number }
type NetworkControls = {
  empty: (target: ApiTarget, data: unknown) => Promise<void>
  failOnce: (target: ApiTarget, status?: number, code?: string) => Promise<void>
  hold: (target: ApiTarget) => Promise<Hold>
}
type TestFixtures = {
  role: Role
  signedIn: Page
  evidence: Evidence
  network: NetworkControls
}
type WorkerFixtures = {
  identity: Identity
  entityCatalog: EntityCatalog
  routeCatalog: RouteCatalog
}

/** All seeding is lazy: --list imports this module without visiting or creating a database. */
function isolatedDirectory(baseURL: unknown): string {
  expect(baseURL, 'Use the repository isolated Playwright configuration').toBe(
    'http://127.0.0.1:5199',
  )
  const directory = process.env.KG_E2E_TEMP_DIR
  expect(directory, 'Only the Playwright temporary database may be used').toBeTruthy()
  const resolved = realpathSync(directory!)
  expect(resolved.startsWith(realpathSync(tmpdir()) + sep)).toBe(true)
  expect(basename(resolved)).toMatch(/^knowledge-e2e-/)
  expect(existsSync(join(resolved, 'metadata.sqlite')), 'Isolated API must have started').toBe(true)
  return resolved
}

export async function responseData<T>(response: APIResponse | Response): Promise<T> {
  expect(response.ok(), `API ${new URL(response.url()).pathname}: HTTP ${response.status()}`).toBe(
    true,
  )
  const envelope = (await response.json()) as { code: string; data: T }
  // These two existing publish endpoints intentionally return the revision directly.
  if (/\/api\/v1\/(domains|ontologies)\/\d+\/publish$/.test(new URL(response.url()).pathname)) {
    expect(envelope).toMatchObject({
      revision: expect.any(Number),
      edit_revision: expect.any(Number),
    })
    return envelope as T
  }
  expect(envelope.code).toBe('KG.OK')
  return envelope.data
}

export async function getData<T>(api: APIRequestContext, path: string): Promise<T> {
  return responseData<T>(await api.get('/api/v1' + path))
}

async function postData<T>(api: APIRequestContext, path: string, data?: unknown): Promise<T> {
  return responseData<T>(await api.post('/api/v1' + path, { data }))
}

export function uniqueName(prefix: string): string {
  return prefix + randomUUID().replaceAll('-', '').slice(0, 12)
}

export async function loginThroughUI(page: Page, credentials: Credentials): Promise<void> {
  await page.goto('/login')
  await page.getByPlaceholder('用户名或邮箱', { exact: true }).fill(credentials.account)
  await page.getByPlaceholder('请输入密码', { exact: true }).fill(credentials.password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { name: '工作台', exact: true })).toBeVisible()
}

export function matchesApi(request: Request, target: ApiTarget): boolean {
  const url = new URL(request.url())
  return (
    url.pathname === '/api/v1' + target.path &&
    request.method() === (target.method ?? 'GET') &&
    Object.entries(target.query ?? {}).every(([key, value]) => url.searchParams.get(key) === value)
  )
}

export function waitForApi(page: Page, target: ApiTarget): Promise<Response> {
  return page.waitForResponse((response) => matchesApi(response.request(), target))
}

export async function settleApi(page: Page, evidence: Evidence): Promise<void> {
  await expect.poll(() => evidence.pending.size, { message: 'Page API requests complete' }).toBe(0)
  await expect(page.locator('.n-spin-body:visible')).toHaveCount(0)
}

export async function expectNoPageOverflow(page: Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }))
  expect(dimensions.document, 'No document-level horizontal overflow').toBeLessThanOrEqual(
    dimensions.viewport + 1,
  )
  expect(dimensions.body, 'No body-level horizontal overflow').toBeLessThanOrEqual(
    dimensions.viewport + 1,
  )
}

export async function attachJson(testInfo: TestInfo, name: string, value: unknown): Promise<void> {
  const path = testInfo.outputPath(name + '.json')
  writeFileSync(path, JSON.stringify(value, null, 2) + '\n')
  await testInfo.attach(name, { path, contentType: 'application/json' })
}

/** Evidence screenshots, not auto-approved pixel baselines. Never hide the state under test. */
export async function capture(
  page: Page,
  testInfo: TestInfo,
  evidence: Evidence,
  name: string,
  state: string,
): Promise<void> {
  await page.evaluate(() => document.fonts.ready)
  await expectNoPageOverflow(page)
  const file = testInfo.outputPath(name + '.png')
  await page.screenshot({ path: file, animations: 'disabled', fullPage: false })
  await testInfo.attach(name, { path: file, contentType: 'image/png' })
  await attachJson(testInfo, name + '-context', {
    url: page.url(),
    viewport: page.viewportSize(),
    browser: page.context().browser()?.version(),
    locale: await page.evaluate(() => navigator.language),
    timezone: await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone),
    state,
    evidenceMode: evidence.injections.length ? 'controlled-network' : 'real-api',
    injections: evidence.injections,
  })
}

export const test = base.extend<TestFixtures, WorkerFixtures>({
  role: ['ADMIN', { option: true }],
  identity: [
    async ({ browser, playwright }, use, workerInfo) => {
      const baseURL = workerInfo.project.use.baseURL
      isolatedDirectory(baseURL)
      const bootstrap = await browser.newPage({ baseURL })
      let api: APIRequestContext | undefined
      try {
        await ensureAdmin(bootstrap)
        const tokens = await responseData<{ access_token: string }>(
          await bootstrap.request.post('/api/v1/auth/login', { data: ADMIN }),
        )
        api = await playwright.request.newContext({
          baseURL,
          extraHTTPHeaders: { Authorization: 'Bearer ' + tokens.access_token },
        })
        const credentials = { ADMIN } as Record<Role, Credentials>
        for (const role of ['EDITOR', 'VIEWER'] as const) {
          const account = uniqueName('ui_' + role.toLowerCase() + '_')
          credentials[role] = { account, password: 'UI-E2E-Password-2026!' }
          const user = await postData<{ role: Role }>(api, '/users', {
            username: account,
            email: account + '@example.org',
            password: credentials[role].password,
            role,
          })
          expect(user.role).toBe(role)
        }
        await use({ api, credentials })
      } finally {
        await api?.dispose()
        await bootstrap.close()
      }
    },
    { scope: 'worker' },
  ],
  entityCatalog: [
    async ({ identity }, use) => {
      const { api } = identity
      const prefix = uniqueName('ui')
      const namespace = await postData<EntityCatalog['namespace']>(api, '/namespaces', {
        prefix,
        iri: 'https://example.org/' + prefix + '/',
        protected: false,
        label_i18n: { 'zh-CN': 'UI 验收命名空间', 'en-US': 'UI acceptance namespace' },
      })
      async function createType(name: string, label: string): Promise<Resource> {
        return postData<Resource>(api, '/entity-types', {
          namespace_id: namespace.id,
          name,
          label_i18n: { 'zh-CN': label, 'en-US': name },
          data_props: [
            {
              name: 'name',
              datatype: 'string',
              nullable: false,
              label_i18n: { 'zh-CN': '名称', 'en-US': 'Name' },
            },
          ],
        })
      }
      const draft = await createType(uniqueName('UiDraft'), 'UI 验收草稿')
      const created = await createType(uniqueName('UiPublished'), 'UI 验收已发布类型')
      await postData(api, '/entity-types/' + created.id + '/publish')
      const published = await getData<Resource>(api, '/entity-types/' + created.id)
      expect(draft.status).toBe('DRAFT')
      expect(published.status).toBe('PUBLISHED')
      expect(published.current_revision).toBe(1)
      await use({ namespace, draft, published })
    },
    { scope: 'worker' },
  ],
  routeCatalog: [
    async ({ identity, entityCatalog }, use, workerInfo) => {
      const { api } = identity
      const { namespace, published } = entityCatalog
      const relation = await postData<Resource>(api, '/relations', {
        name: uniqueName('UiRelation'),
        namespace_id: namespace.id,
        label_i18n: { 'zh-CN': 'UI 验收关系', 'en-US': 'UI acceptance relation' },
        domain_spec: { type_id: published.id },
        range_spec: { type_id: published.id },
      })
      await postData(api, '/relations/' + relation.id + '/publish')
      const memberIds = [published.id, relation.id]
      const domain = await postData<Resource>(api, '/domains', {
        name: uniqueName('UiDomain'),
        iri: 'https://example.org/' + uniqueName('domain') + '/',
        label_i18n: { 'zh-CN': 'UI 验收业务域', 'en-US': 'UI acceptance domain' },
        member_ids: memberIds,
      })
      await postData(api, '/domains/' + domain.id + '/publish')
      const ontology = await postData<Resource>(api, '/ontologies', {
        name: uniqueName('UiOntology'),
        iri: 'https://example.org/' + uniqueName('ontology') + '/',
        label_i18n: { 'zh-CN': 'UI 验收本体', 'en-US': 'UI acceptance ontology' },
        ref_resource_ids: memberIds,
      })
      await postData(api, '/ontologies/' + ontology.id + '/publish')
      const directory = isolatedDirectory(workerInfo.project.use.baseURL)
      const sourcePath = join(directory, uniqueName('ui-source-') + '.sqlite')
      copyFileSync(resolve('samples/enterprise_demo.sqlite'), sourcePath)
      const source = await postData<{ id: number }>(api, '/datasources', {
        name: uniqueName('UiSource'),
        kind: 'sqlite',
        params: { database: sourcePath },
      })
      await postData(api, '/datasources/' + source.id + '/metadata/capture')
      const mapping = await postData<{ id: number; current_revision: number }>(api, '/mappings', {
        name: uniqueName('UiMapping'),
        ontology_id: ontology.id,
        draft: {
          entity_maps: [
            {
              entity_type: published.name,
              table: 'enterprise',
              schema: 'main',
              key_fields: ['id'],
              field_maps: [{ target_attr: 'name', source_field: 'name', null_policy: 'REQUIRED' }],
            },
          ],
          rel_maps: [],
        },
      })
      const revision = await postData<{ id: number }>(api, '/mappings/' + mapping.id + '/publish', {
        if_match: mapping.current_revision,
      })
      const result = await postData<{
        run: { id: number; status: string }
        graph_revision: { id: number }
      }>(api, '/extraction/runs', {
        mapping_revision_id: revision.id,
        datasource_id: source.id,
        namespace: ontology.iri,
      })
      expect(result.run.status).toBe('SUCCESS')
      const entities = await getData<Array<{ iri: string }>>(
        api,
        '/extraction/graph/' + result.graph_revision.id + '/entities?page=1&page_size=20',
      )
      expect(
        entities.length,
        'G03 requires a real extracted entity, never a guessed ID',
      ).toBeGreaterThan(0)
      await use({
        ...entityCatalog,
        relation,
        domain,
        ontology,
        datasourceId: source.id,
        mappingId: mapping.id,
        runId: result.run.id,
        graphId: result.graph_revision.id,
        entityIri: entities[0].iri,
      })
    },
    { scope: 'worker' },
  ],
  evidence: [
    async ({ page }, use, testInfo) => {
      const evidence: Evidence = {
        pending: new Set(),
        responses: [],
        pageErrors: [],
        failedRequests: [],
        allowedFailures: [],
        injections: [],
      }
      const started = (request: Request) => {
        if (new URL(request.url()).pathname.startsWith('/api/v1/')) evidence.pending.add(request)
      }
      const finished = (request: Request) => evidence.pending.delete(request)
      const transportFailed = (request: Request) => {
        finished(request)
        const path = new URL(request.url()).pathname
        const reason = request.failure()?.errorText ?? 'Unknown transport failure'
        // Navigation and the list's AbortController legitimately cancel superseded GETs.
        if (path.startsWith('/api/v1/') && !reason.includes('ERR_ABORTED')) {
          evidence.failedRequests.push(request.method() + ' ' + path + ': ' + reason)
        }
      }
      const responded = (response: Response) => {
        const path = new URL(response.url()).pathname
        if (path.startsWith('/api/v1/')) {
          evidence.responses.push({
            path,
            method: response.request().method(),
            status: response.status(),
          })
        }
      }
      const failed = (error: Error) => evidence.pageErrors.push(error.message)
      page.on('request', started)
      page.on('requestfinished', finished)
      page.on('requestfailed', transportFailed)
      page.on('response', responded)
      page.on('pageerror', failed)
      await use(evidence)
      page.off('request', started)
      page.off('requestfinished', finished)
      page.off('requestfailed', transportFailed)
      page.off('response', responded)
      page.off('pageerror', failed)
      await attachJson(testInfo, 'browser-observations', {
        responses: evidence.responses,
        pageErrors: evidence.pageErrors,
        failedRequests: evidence.failedRequests,
        injections: evidence.injections,
      })
      expect(evidence.pageErrors, 'No uncaught browser exceptions').toEqual([])
      expect(evidence.failedRequests, 'No unexpected API transport failures').toEqual([])
      expect(
        evidence.responses.filter(
          (entry) =>
            entry.status >= 400 &&
            !evidence.allowedFailures.some(
              (allowed) =>
                allowed.path === entry.path &&
                allowed.method === entry.method &&
                allowed.status === entry.status,
            ),
        ),
        'No unexpected API failures',
      ).toEqual([])
    },
    { auto: true },
  ],
  signedIn: async ({ page, identity, role, evidence }, use) => {
    await loginThroughUI(page, identity.credentials[role])
    await settleApi(page, evidence)
    await use(page)
  },
  network: async ({ page, evidence }, use) => {
    const cleanups: Array<() => Promise<void>> = []
    async function install(target: ApiTarget, action: (route: Route) => Promise<void>) {
      const matcher = (url: URL) => url.pathname === '/api/v1' + target.path
      const handler = async (route: Route) => {
        if (matchesApi(route.request(), target)) await action(route)
        else await route.fallback()
      }
      await page.route(matcher, handler)
      cleanups.push(() => page.unroute(matcher, handler))
    }
    const controls: NetworkControls = {
      async empty(target, data) {
        const injection: Injection = { ...target, kind: 'empty', hits: 0 }
        evidence.injections.push(injection)
        await install(target, async (route) => {
          injection.hits++
          await route.fulfill({ status: 200, json: { code: 'KG.OK', data } })
        })
      },
      async failOnce(target, status = 503, code = 'KG.INTERNAL_ERROR') {
        const injection: Injection = { ...target, kind: 'failure', hits: 0 }
        evidence.injections.push(injection)
        evidence.allowedFailures.push({
          path: '/api/v1' + target.path,
          method: target.method ?? 'GET',
          status,
        })
        await install(target, async (route) => {
          if (injection.hits) return route.fallback()
          injection.hits++
          await route.fulfill({ status, json: { code, message: '', params: {}, data: null } })
        })
      },
      async hold(target) {
        let release = () => {}
        const released = new Promise<void>((resolveRelease) => {
          release = resolveRelease
        })
        const injection: Injection = { ...target, kind: 'delay', hits: 0 }
        evidence.injections.push(injection)
        await install(target, async (route) => {
          injection.hits++
          await released
          await route.fallback()
        })
        cleanups.push(async () => {
          release()
        })
        return { release, hits: () => injection.hits }
      },
    }
    try {
      await use(controls)
    } finally {
      for (const cleanup of cleanups.reverse()) await cleanup()
    }
  },
})

export { expect } from '@playwright/test'
