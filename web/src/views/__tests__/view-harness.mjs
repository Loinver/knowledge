import 'naive-ui'

import { randomUUID } from 'node:crypto'
import { mkdir, readFile, unlink } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { compileScript, parse } from '@vue/compiler-sfc'
import { build } from 'esbuild'
import { createPinia } from 'pinia'
import { createRenderer, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

export const root = fileURLToPath(new URL('../../../../', import.meta.url))
const out = path.join(root, 'web/node_modules/.tmp')
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

export async function compile(entry, stubs = {}, expose = '', transform = (s) => s) {
  const id = `audit_${randomUUID().replaceAll('-', '')}`
  globalThis[id] = stubs
  const entryPoint = path.join(root, 'web/src', entry)
  const outfile = path.join(out, `${id}.mjs`)
  await mkdir(out, { recursive: true })
  await build({
    entryPoints: [entryPoint],
    outfile,
    bundle: true,
    platform: 'node',
    format: 'esm',
    packages: 'external',
    logLevel: 'silent',
    plugins: [
      {
        name: 'audit-readonly',
        setup(b) {
          b.onResolve({ filter: /^naive-ui$/ }, ({ namespace, path }) =>
            namespace === 'message-stub'
              ? { path, external: true }
              : { path, namespace: 'message-stub' },
          )
          b.onLoad({ filter: /.*/, namespace: 'message-stub' }, () => ({
            contents:
              "export * from 'naive-ui'; export const useMessage = () => ({success(){},error(){},warning(){},info(){}})",
          }))
          b.onResolve({ filter: /^@\/api\// }, (args) =>
            stubs[args.path] ? { path: args.path, namespace: 'stub' } : undefined,
          )
          b.onLoad({ filter: /.*/, namespace: 'stub' }, ({ path: p }) => ({
            contents: Object.keys(stubs[p])
              .map(
                (k) =>
                  `export const ${k} = globalThis[${JSON.stringify(id)}][${JSON.stringify(p)}][${JSON.stringify(k)}]`,
              )
              .join('\n'),
          }))
          b.onResolve({ filter: /^@\// }, ({ path: p, kind, resolveDir }) =>
            b.resolve(path.join(root, 'web/src', p.slice(2)), { kind, resolveDir }),
          )
          b.onLoad({ filter: /\.ts$/ }, async ({ path: filename }) =>
            filename === entryPoint
              ? {
                  contents: transform(await readFile(filename, 'utf8')),
                  loader: 'ts',
                  resolveDir: path.dirname(filename),
                }
              : undefined,
          )
          b.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
            if (filename !== entryPoint) return { contents: 'export default {render:()=>null}' }
            const original = transform(await readFile(filename, 'utf8'))
            const source = expose
              ? original
                  .replace(/defineExpose\(\{[^}]*\}\)/g, '')
                  .replace('</script>', `\ndefineExpose({${expose}})\n</script>`)
              : original
            const { descriptor } = parse(source, { filename })
            return {
              contents: compileScript(descriptor, { id }).content,
              loader: 'ts',
              resolveDir: path.dirname(filename),
            }
          })
        },
      },
    ],
  })
  const mod = await import(pathToFileURL(outfile).href)
  await unlink(outfile)
  return { mod, cleanup: () => delete globalThis[id] }
}

export async function mount(entry, stubs, expose, start = '/', transform) {
  const built = await compile(entry, stubs, expose, transform)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/entities/:id', component: { render: () => null } },
      { path: '/:pathMatch(.*)*', component: { render: () => null } },
    ],
  })
  await router.push(start)
  const i18n = createI18n({
    legacy: false,
    locale: 'en-US',
    messages: {
      'en-US': JSON.parse(await readFile(path.join(root, 'web/src/locales/en-US.json'), 'utf8')),
    },
  })
  const app = renderer
    .createApp({ ...built.mod.default, render: () => null })
    .use(router)
    .use(i18n)
    .use(createPinia())
  const vm = app.mount({})
  await settle()
  return {
    vm,
    router,
    stop: () => {
      app.unmount()
      built.cleanup()
    },
  }
}
