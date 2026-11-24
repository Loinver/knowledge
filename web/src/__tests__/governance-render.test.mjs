import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { mkdir, readFile, unlink } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { compileScript, compileTemplate, parse, registerTS } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { build } from 'esbuild'
import { createPinia } from 'pinia'
import { createSSRApp } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

const pageFiles = {
  EnumDictionaries: 'semantic-assets/configuration/enum-dictionaries/EnumDictionariesPage',
  AssemblyTemplates: 'semantic-assets/configuration/assembly-templates/AssemblyTemplatesPage',
  StandardClauses: 'governance/clauses/StandardClausesPage',
  GovernanceRules: 'governance/rules/GovernanceRulesPage',
  OntologyExport: 'governance/exchange/OntologyExchangePage',
}

const web = fileURLToPath(new URL('../..', import.meta.url))
const resolvePackage = createRequire(path.join(web, 'package.json'))
registerTS(() => resolvePackage('typescript'))
const outputDir = path.join(web, 'node_modules/.tmp')
const escapeHtml = (text) =>
  text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')

test('Chinese and English locale keys stay aligned', async () => {
  const keys = (value, prefix = '') =>
    Object.entries(value)
      .flatMap(([key, child]) =>
        typeof child === 'object' ? keys(child, `${prefix}${key}.`) : [`${prefix}${key}`],
      )
      .sort()
  const readLocale = async (locale) =>
    JSON.parse(await readFile(path.join(web, `src/locales/${locale}.json`), 'utf8'))
  assert.deepEqual(keys(await readLocale('zh-CN')), keys(await readLocale('en-US')))
})

// Compile the real templates without opening a browser or calling a live API.
async function component(name) {
  await mkdir(outputDir, { recursive: true })
  const outfile = path.join(outputDir, `governance-render-${randomUUID()}.mjs`)
  try {
    await build({
      entryPoints: [path.join(web, `src/views/${pageFiles[name]}.vue`)],
      outfile,
      bundle: true,
      platform: 'node',
      format: 'esm',
      packages: 'external',
      loader: { '.css': 'empty' },
      logLevel: 'silent',
      plugins: [
        {
          name: 'vue-ssr',
          setup(bundler) {
            bundler.onResolve(
              { filter: /^@\/api\/(governance|client|templates)$/ },
              ({ path }) => ({
                path,
                namespace: 'api-stub',
              }),
            )
            bundler.onLoad({ filter: /.*/, namespace: 'api-stub' }, () => ({
              contents:
                'export const rulesApi = {list: async () => ({items: [], total: 0})}; export const templatesApi = {list: async () => ({items: [], total: 0}), resources: async () => [], ontologies: async () => []}; export const http = {get: async () => ({data: []})}',
            }))
            bundler.onResolve({ filter: /^@\// }, ({ path: module, kind, resolveDir }) =>
              bundler.resolve(path.join(web, 'src', module.slice(2)), { kind, resolveDir }),
            )
            bundler.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
              const { descriptor } = parse(await readFile(filename, 'utf8'), { filename })
              if (!descriptor.script && !descriptor.scriptSetup) {
                const template = compileTemplate({
                  source: descriptor.template?.content ?? '',
                  filename,
                  id: name,
                  ssr: true,
                  ssrCssVars: descriptor.cssVars,
                })
                assert.deepEqual(template.errors, [])
                return {
                  contents: `${template.code}\nexport default {ssrRender}`,
                  loader: 'ts',
                  resolveDir: path.dirname(filename),
                }
              }
              const script = compileScript(descriptor, {
                id: name,
                inlineTemplate: true,
                templateOptions: { ssr: true },
                fs: { fileExists: existsSync, readFile: (value) => readFileSync(value, 'utf8') },
              })
              return { contents: script.content, loader: 'ts', resolveDir: path.dirname(filename) }
            })
          },
        },
      ],
    })
    return (await import(pathToFileURL(outfile).href)).default
  } finally {
    await unlink(outfile).catch(() => {})
  }
}

for (const [name, heading, action] of [
  ['GovernanceRules', 'page.governanceRules', 'rules.create'],
  ['OntologyExport', 'ui.exchange', 'export.download'],
  ['AssemblyTemplates', 'templates.title', 'templates.create'],
]) {
  test(`${name} renders both locales with real templates and no untranslated keys`, async () => {
    const view = await component(name)
    for (const locale of ['zh-CN', 'en-US']) {
      const messages = JSON.parse(
        await readFile(path.join(web, `src/locales/${locale}.json`), 'utf8'),
      )
      const i18n = createI18n({ legacy: false, locale, messages: { [locale]: messages } })
      const router = createRouter({
        history: createMemoryHistory(),
        routes: [{ path: '/', component: view }],
      })
      await router.push('/')
      await router.isReady()
      const pinia = createPinia()
      pinia.state.value.auth = {
        user: { id: 1, role: 'EDITOR', status: 'ACTIVE', username: 'test_actor' },
      }
      const app = createSSRApp(view).use(i18n).use(router).use(pinia)
      const html = await renderToString(app)
      assert.ok(html.includes(escapeHtml(i18n.global.t(heading))))
      assert.ok(html.includes(escapeHtml(i18n.global.t(action))))
      assert.doesNotMatch(html, />(rules|export|governanceUi)\.[A-Za-z]+</)
      if (locale === 'en-US') assert.doesNotMatch(html, /[\u4e00-\u9fff]/)
      if (name === 'OntologyExport') assert.match(html, /disabled/)
    }
  })
}
