import { randomUUID } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { readFile, unlink, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { compileScript, parse } from '@vue/compiler-sfc'
import { build } from 'esbuild'
import { createRenderer, h, nextTick, shallowReactive } from 'vue'
import { createI18n } from 'vue-i18n'

const root = fileURLToPath(new URL('../../../../../', import.meta.url))
const resolvePackage = createRequire(path.join(root, 'web/package.json'))
export async function component(entry) {
  const id = `table_test_${randomUUID().replaceAll('-', '')}`
  const output = `/private/tmp/${id}.mjs`
  const result = await build({
    entryPoints: [path.join(root, 'web/src', entry)],
    bundle: true,
    platform: 'node',
    format: 'esm',
    write: false,
    logLevel: 'silent',
    plugins: [
      {
        name: 'render-real-vue-components',
        setup(b) {
          b.onResolve({ filter: /^@\// }, ({ path: value, kind, resolveDir }) =>
            b.resolve(path.join(root, 'web/src', value.slice(2)), { kind, resolveDir }),
          )
          b.onResolve({ filter: /^[^./]/ }, ({ path: value }) => ({
            path: resolvePackage.resolve(value),
            external: true,
          }))
          b.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
            const { descriptor } = parse(await readFile(filename, 'utf8'), { filename })
            return {
              contents: compileScript(descriptor, {
                id,
                inlineTemplate: true,
                fs: { fileExists: existsSync, readFile: (file) => readFileSync(file, 'utf8') },
              }).content,
              loader: 'ts',
              resolveDir: path.dirname(filename),
            }
          })
        },
      },
    ],
  })
  await writeFile(output, result.outputFiles[0].text)
  try {
    return (await import(pathToFileURL(output).href)).default
  } finally {
    await unlink(output)
  }
}
function node(type, text = '') {
  return { type, text, props: {}, style: {}, children: [], parent: null }
}
const renderer = createRenderer({
  createElement: (type) => node(type),
  createText: (text) => node('#text', text),
  createComment: (text) => node('#comment', text),
  setText: (n, text) => {
    n.text = text
  },
  setElementText: (n, text) => {
    n.text = text
    n.children = []
  },
  parentNode: (n) => n.parent,
  nextSibling: (n) => n.parent?.children[n.parent.children.indexOf(n) + 1] ?? null,
  insert(n, parent, anchor) {
    if (n.parent) n.parent.children.splice(n.parent.children.indexOf(n), 1)
    n.parent = parent
    const index = anchor ? parent.children.indexOf(anchor) : -1
    if (index < 0) parent.children.push(n)
    else parent.children.splice(index, 0, n)
  },
  remove(n) {
    if (n.parent) n.parent.children.splice(n.parent.children.indexOf(n), 1)
    n.parent = null
  },
  patchProp: (n, key, _previous, value) => {
    n.props[key] = value
  },
})
export async function mount(Component, input, slots = {}, locale = 'en-US') {
  const props = shallowReactive({ ...input })
  const container = node('root')
  const app = renderer.createApp({ render: () => h(Component, props, slots) })
  app.use(
    createI18n({
      legacy: false,
      locale,
      messages: {
        [locale]: JSON.parse(
          await readFile(path.join(root, `web/src/locales/${locale}.json`), 'utf8'),
        ),
      },
    }),
  )
  app.mount(container)
  await nextTick()
  return {
    tree: container,
    props,
    stop: () => app.unmount(),
    update: async (next) => {
      Object.assign(props, next)
      await nextTick()
      await nextTick()
    },
  }
}
export function find(tree, predicate) {
  return [tree, ...tree.children.flatMap((child) => find(child, predicate))].filter(predicate)
}
export function text(tree) {
  return (tree.type === '#comment' ? '' : tree.text) + tree.children.map(text).join('')
}
export async function dispatch(n, event, extra = {}) {
  const args = {
    target: { closest: () => null },
    preventDefault() {},
    stopPropagation() {},
    ...extra,
  }
  const handlers = n.props[event]
  for (const handler of Array.isArray(handlers) ? handlers : [handlers]) handler?.(args)
  await nextTick()
  return args
}
