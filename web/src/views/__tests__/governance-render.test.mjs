import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { mkdir, readFile, unlink } from 'node:fs/promises'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { setup } from '@css-render/vue3-ssr'
import { compileScript, parse } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { build } from 'esbuild'
import { createSSRApp } from 'vue'
import { createI18n } from 'vue-i18n'

const web = fileURLToPath(new URL('../../..', import.meta.url))
const outputDir = path.join(web, 'node_modules/.tmp')

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
      entryPoints: [path.join(web, `src/views/${name}.vue`)],
      outfile,
      bundle: true,
      platform: 'node',
      format: 'esm',
      packages: 'external',
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
            bundler.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
              const { descriptor } = parse(await readFile(filename, 'utf8'), { filename })
              const script = compileScript(descriptor, {
                id: name,
                inlineTemplate: true,
                templateOptions: { ssr: true },
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
  ['OntologyExport', 'export.title', 'export.download'],
  ['AssemblyTemplates', 'templates.title', 'templates.create'],
]) {
  test(`${name} renders both locales with real templates and no untranslated keys`, async () => {
    const view = await component(name)
    for (const locale of ['zh-CN', 'en-US']) {
      const messages = JSON.parse(
        await readFile(path.join(web, `src/locales/${locale}.json`), 'utf8'),
      )
      const i18n = createI18n({ legacy: false, locale, messages: { [locale]: messages } })
      const app = createSSRApp(view).use(i18n)
      setup(app)
      const html = await renderToString(app)
      assert.ok(html.includes(i18n.global.t(heading)))
      assert.ok(html.includes(i18n.global.t(action)))
      assert.doesNotMatch(html, />(rules|export)\.[A-Za-z]+</)
      if (locale === 'en-US') assert.doesNotMatch(html, /[\u4e00-\u9fff]/)
      if (name === 'OntologyExport') assert.match(html, /disabled/)
    }
  })
}
