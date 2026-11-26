import { randomUUID } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { readFile, unlink, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { compileScript, compileTemplate, parse, registerTS } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { build } from 'esbuild'
import { createPinia } from 'pinia'
import { createRenderer, createSSRApp, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

export const root = fileURLToPath(new URL('../../../../../../', import.meta.url))
const resolvePackage = createRequire(path.join(root, 'web/package.json'))
registerTS(() => resolvePackage('typescript'))
export const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
export const settle = async () => {
  await new Promise(setImmediate)
  await nextTick()
  await new Promise(setImmediate)
}
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

async function compile(entry, api, expose, seed = '', ssr = false) {
  const id = `catalog_${randomUUID().replaceAll('-', '')}`
  globalThis[id] = api
  const filename = path.join(root, 'web/src/views/data-integration/catalog', entry)
  const outfile = `/private/tmp/${id}.mjs`
  const result = await build({
    entryPoints: [filename],
    bundle: true,
    write: false,
    platform: 'node',
    format: 'esm',
    loader: { '.css': 'empty' },
    logLevel: 'silent',
    plugins: [
      {
        name: 'catalog-private-tests',
        setup(b) {
          b.onResolve({ filter: /^@\/api\/datasources$/ }, () => ({
            path: 'datasources',
            namespace: id,
          }))
          b.onLoad({ filter: /.*/, namespace: id }, () => ({
            contents: `export const datasourcesApi = globalThis[${JSON.stringify(id)}].datasourcesApi; export const metadataApi = globalThis[${JSON.stringify(id)}].metadataApi`,
          }))
          b.onResolve({ filter: /^@\// }, ({ path: value, kind, resolveDir }) =>
            b.resolve(path.join(root, 'web/src', value.slice(2)), { kind, resolveDir }),
          )
          // Absolute external paths allow all test artifacts to stay in /private/tmp.
          b.onResolve({ filter: /^[^./]/ }, async ({ path: value, pluginData }) => {
            if (pluginData?.externalize) return undefined
            const resolved = await b.resolve(value, {
              kind: 'import-statement',
              resolveDir: path.join(root, 'web'),
              pluginData: { externalize: true },
            })
            return resolved.errors.length
              ? { errors: resolved.errors }
              : { path: resolved.path, external: true }
          })
          b.onLoad({ filter: /\.vue$/ }, async ({ path: file }) => {
            if (!ssr && file !== filename) return { contents: 'export default {render:()=>null}' }
            let source = await readFile(file, 'utf8')
            if (file === filename)
              source = source.replace(
                '</script>',
                `${seed}\n${expose ? `defineExpose({${expose}})` : ''}\n</script>`,
              )
            const { descriptor } = parse(source, { filename: file })
            if (!descriptor.script && !descriptor.scriptSetup) {
              const compiled = compileTemplate({
                source: descriptor.template.content,
                filename: file,
                id,
                ssr,
              })
              if (compiled.errors.length) throw new Error(compiled.errors.join('\n'))
              return {
                contents: `${compiled.code}\nexport default {ssrRender}`,
                loader: 'ts',
                resolveDir: path.dirname(file),
              }
            }
            return {
              contents: compileScript(descriptor, {
                id,
                inlineTemplate: ssr,
                templateOptions: { ssr },
                fs: { fileExists: existsSync, readFile: (value) => readFileSync(value, 'utf8') },
              }).content,
              loader: 'ts',
              resolveDir: path.dirname(file),
            }
          })
        },
      },
    ],
  })
  await writeFile(outfile, result.outputFiles[0].text)
  try {
    return { mod: await import(pathToFileURL(outfile).href), cleanup: () => delete globalThis[id] }
  } finally {
    await unlink(outfile)
  }
}

async function context(start, role, locale = 'en-US') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/catalog', name: 'data-catalog', component: { render: () => null } },
      { path: '/preview', name: 'sample-preview', component: { render: () => null } },
    ],
  })
  await router.push(start)
  const pinia = createPinia()
  pinia.state.value.auth = { user: { id: 1, username: 'example_actor', role, status: 'ACTIVE' } }
  const messages = JSON.parse(
    await readFile(path.join(root, `web/src/locales/${locale}.json`), 'utf8'),
  )
  const i18n = createI18n({ legacy: false, locale, messages: { [locale]: messages } })
  return { router, pinia, i18n }
}

export async function mount(entry, api, expose, start = '/catalog', role = 'EDITOR', props = {}) {
  const built = await compile(entry, api, expose)
  const ctx = await context(start, role)
  const app = renderer
    .createApp({ ...built.mod.default, render: () => null }, props)
    .use(ctx.router)
    .use(ctx.pinia)
    .use(ctx.i18n)
  const vm = app.mount({})
  await settle()
  return {
    vm,
    ...ctx,
    updateProps: async (next) => {
      Object.assign(app._instance.props, next)
      await settle()
    },
    stop: () => {
      app.unmount()
      built.cleanup()
    },
  }
}

export async function render(entry, seed, start = '/catalog', role = 'EDITOR', locale = 'en-US') {
  const pending = () => new Promise(() => {})
  const api = {
    datasourcesApi: { list: pending, preview: pending },
    metadataApi: {
      latest: pending,
      snapshots: pending,
      get: pending,
      capture: pending,
      references: pending,
    },
  }
  const built = await compile(entry, api, '', seed, true)
  const ctx = await context(start, role, locale)
  try {
    const html = await renderToString(
      createSSRApp(built.mod.default).use(ctx.router).use(ctx.pinia).use(ctx.i18n),
    )
    return { html, t: ctx.i18n.global.t }
  } finally {
    built.cleanup()
  }
}
