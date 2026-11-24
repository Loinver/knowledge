import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { readFile, unlink, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { compileScript, compileTemplate, parse, registerTS } from '@vue/compiler-sfc'
import { build } from 'esbuild'
import { createPinia } from 'pinia'
import { createRenderer } from 'vue'
import { createI18n } from 'vue-i18n'

import { settle } from '../../../testing/view-harness.mjs'

const web = fileURLToPath(new URL('../../../..', import.meta.url))
const resolvePackage = createRequire(path.join(web, 'package.json'))
registerTS(() => resolvePackage('typescript'))
globalThis.Document ??= class {}
globalThis.ShadowRoot ??= class {}
export function find(tree, predicate) {
  return [tree, ...tree.children.flatMap((child) => find(child, predicate))].filter(predicate)
}
export function contents(tree) {
  return (tree.type === '#comment' ? '' : tree.text) + tree.children.map(contents).join('')
}
function node(type, text = '') {
  return {
    // Native DOM elements are not made reactive by Vue; preserve the same identity here.
    __v_skip: true,
    type,
    tagName: type.toUpperCase(),
    text,
    props: {},
    children: [],
    parent: null,
    listeners: new Map(),
    getRootNode() {
      return this.parent?.getRootNode() ?? this
    },
    focus() {
      if (this.props.disabled) return
      this.getRootNode().activeElement = this
    },
    addEventListener(event, callback) {
      const listeners = this.listeners.get(event) ?? []
      listeners.push(callback)
      this.listeners.set(event, listeners)
    },
    removeEventListener(event, callback) {
      this.listeners.set(
        event,
        (this.listeners.get(event) ?? []).filter((listener) => listener !== callback),
      )
    },
    getAttribute(name) {
      return this.props[name] ?? null
    },
    querySelector(selector) {
      return find(this, (item) => selector.split(',').includes(item.type))[0] ?? null
    },
  }
}
const renderer = createRenderer({
  createElement: (type) => node(type),
  createText: (text) => node('#text', text),
  createComment: (text) => node('#comment', text),
  setText: (item, text) => {
    item.text = text
  },
  setElementText: (item, text) => {
    item.text = text
    item.children = []
  },
  parentNode: (item) => item.parent,
  nextSibling: (item) => item.parent?.children[item.parent.children.indexOf(item) + 1] ?? null,
  insert(item, parent, anchor) {
    if (item.parent) item.parent.children.splice(item.parent.children.indexOf(item), 1)
    item.parent = parent
    const index = anchor ? parent.children.indexOf(anchor) : -1
    if (index < 0) parent.children.push(item)
    else parent.children.splice(index, 0, item)
  },
  remove(item) {
    item.parent?.children.splice(item.parent.children.indexOf(item), 1)
    item.parent = null
  },
  patchProp: (item, key, _previous, value) => {
    item.props[key] = value
  },
})

async function compile(entryName, api, notices, expose, session) {
  const entry = path.join(web, 'src', entryName)
  const key = `c4_form_${randomUUID()}`
  const outfile = `/private/tmp/${key}.mjs`
  globalThis[key] = { api, notices, session }
  try {
    const result = await build({
      entryPoints: [entry],
      outfile,
      write: false,
      bundle: true,
      platform: 'node',
      format: 'esm',
      logLevel: 'silent',
      loader: { '.css': 'empty' },
      plugins: [
        {
          name: 'c4-real-form-and-table',
          setup(builder) {
            builder.onResolve(
              {
                filter:
                  /^(vue-router|@\/api\/auth|@\/api\/ai-models|@\/api\/tokens|@\/components\/ui)$/,
              },
              ({ path: value }) => ({ path: value, namespace: 'stub' }),
            )
            builder.onLoad({ filter: /.*/, namespace: 'stub' }, ({ path: value }) => ({
              resolveDir: web,
              contents:
                value === 'vue-router'
                  ? `import {h} from 'vue'; export const RouterLink = {props:['to'], setup(p,{slots}) {return()=>h('a', {}, slots.default?.())}}; export const onBeforeRouteLeave = () => {}; export const useRoute = () => globalThis[${JSON.stringify(key)}].session.route; export const useRouter = () => ({replace: async target=>{globalThis[${JSON.stringify(key)}].session.redirects.push(target)},push:async()=>{}})`
                  : value === '@/components/ui'
                    ? `export * from ${JSON.stringify(path.join(web, 'src/components/ui/index.ts'))}; export const useMessage = () => Object.fromEntries(['success','error','warning','info'].map(kind=>[kind, text=>globalThis[${JSON.stringify(key)}].notices.push({kind,text})]));`
                    : value === '@/api/tokens'
                      ? `export const getSessionGeneration = () => globalThis[${JSON.stringify(key)}].session.generation; export const getAccessToken = () => 'fixture'; export const hasSession = () => true; export const subscribeTokens = () => () => {}; export const clearTokens = () => {}; export const storeTokens = () => true;`
                      : `export const ${value === '@/api/auth' ? 'authApi' : 'aiModelsApi'} = globalThis[${JSON.stringify(key)}].api`,
            }))
            builder.onResolve({ filter: /^@\// }, ({ path: value, kind, resolveDir }) =>
              builder.resolve(path.join(web, 'src', value.slice(2)), { kind, resolveDir }),
            )
            builder.onResolve({ filter: /^[^./]/ }, ({ path: value }) => ({
              path:
                value === 'class-variance-authority'
                  ? resolvePackage.resolve(value).replace(/index\.js$/, 'index.mjs')
                  : resolvePackage.resolve(value),
              external: true,
            }))
            builder.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
              // Reka overlays/combobox DOM behavior belongs to the Chief's browser run.
              // Keep the page's real Form/Field/Input/Number and SearchPanel/SearchTable.
              if (
                filename.endsWith('/primitives/switch/Switch.vue') ||
                filename.endsWith('/primitives/checkbox/Checkbox.vue')
              )
                return {
                  contents: `import {h} from 'vue'; export default {props:['modelValue','disabled'],emits:['update:modelValue'],setup(p,{emit}) {return()=>h('button',{type:'button',disabled:p.disabled,'aria-checked':p.modelValue,onClick:()=>!p.disabled&&emit('update:modelValue',!p.modelValue)})}}`,
                  loader: 'ts',
                  resolveDir: path.dirname(filename),
                }
              if (filename.endsWith('/UiSelect.vue'))
                return {
                  contents: `import {h} from 'vue'; export default {props:['value','options'],emits:['update:value'],setup(p,{emit}) {return()=>h('select',{value:p.value,onChange:e=>emit('update:value',e.target.value)},p.options?.map(o=>h('option',{value:o.value},o.label)))}}`,
                  loader: 'ts',
                  resolveDir: path.dirname(filename),
                }
              if (filename.endsWith('/UiModal.vue') || filename.endsWith('/UiDrawer.vue'))
                return {
                  contents: `import {h} from 'vue'; export default {props:['show'],setup(p,{slots}) {return()=>p.show?h('section',{},[slots.default?.(),slots.footer?.()]):null}}`,
                  loader: 'ts',
                  resolveDir: path.dirname(filename),
                }
              if (filename.endsWith('/UiDrawerContent.vue'))
                return {
                  contents: `import {h} from 'vue'; export default {setup(p,{slots}) {return()=>h('section',{},[slots.default?.(),slots.footer?.()])}}`,
                  loader: 'ts',
                  resolveDir: path.dirname(filename),
                }
              if (filename.endsWith('/UiPopconfirm.vue'))
                return {
                  contents: `import {h} from 'vue'; export default {setup(p,{slots}) {return()=>h('div',{},slots.trigger?.())}}`,
                  loader: 'ts',
                  resolveDir: path.dirname(filename),
                }
              let source = await readFile(filename, 'utf8')
              if (filename === entry && expose)
                source = source.replace('</script>', `\ndefineExpose({${expose}})\n</script>`)
              const id = `${key}-${filename}`
              const { descriptor } = parse(source, { filename })
              const script =
                descriptor.script || descriptor.scriptSetup
                  ? compileScript(descriptor, {
                      id,
                      inlineTemplate: true,
                      fs: {
                        fileExists: existsSync,
                        readFile: (file) => readFileSync(file, 'utf8'),
                      },
                    }).content
                  : (() => {
                      const template = compileTemplate({
                        source: descriptor.template.content,
                        filename,
                        id,
                      })
                      assert.deepEqual(template.errors, [])
                      return `${template.code}\nexport default {render}`
                    })()
              return { contents: script, loader: 'ts', resolveDir: path.dirname(filename) }
            })
          },
        },
      ],
    })
    await writeFile(outfile, result.outputFiles[0].text)
    return {
      component: (await import(pathToFileURL(outfile).href)).default,
      cleanup: () => delete globalThis[key],
    }
  } catch (error) {
    delete globalThis[key]
    throw error
  } finally {
    await unlink(outfile).catch(() => {})
  }
}

export async function mountC4(t, entry, api, expose, role = 'ADMIN', start = '/') {
  const notices = []
  const { reactive } = await import('vue')
  const session = reactive({
    generation: 'c4-session',
    route: { fullPath: start, query: {} },
    redirects: [],
  })
  const built = await compile(entry, api, notices, expose, session)
  const messages = {}
  for (const language of ['en-US', 'zh-CN'])
    messages[language] = JSON.parse(
      await readFile(path.join(web, `src/locales/${language}.json`), 'utf8'),
    )
  const i18n = createI18n({ legacy: false, locale: 'en-US', messages })
  const pinia = createPinia()
  pinia.state.value.auth = { user: { id: 'actor', role, status: 'ACTIVE', username: 'test_actor' } }
  const tree = node('root')
  const app = renderer.createApp(built.component).use(i18n).use(pinia)
  const vm = app.mount(tree)
  let stopped = false
  const stop = () => {
    if (stopped) return
    stopped = true
    app.unmount()
    built.cleanup()
  }
  t.after(stop)
  await settle()
  return {
    vm,
    tree,
    i18n,
    notices,
    session,
    stop,
    field(label) {
      return find(tree, (n) => ['input', 'textarea', 'select'].includes(n.type)).find(
        (n) =>
          n.props['aria-label'] === label ||
          contents(
            find(tree, (item) => item.props.id === n.props['aria-labelledby'])[0] ?? node('#empty'),
          ).startsWith(label),
      )
    },
    invalid: () =>
      find(
        tree,
        (n) => ['input', 'textarea', 'select'].includes(n.type) && n.props['aria-invalid'],
      ),
  }
}
export async function input(control, value) {
  assert.ok(control, 'missing control')
  assert.ok(!control.props.disabled)
  control.value = value
  control.props.onInput?.({ target: control })
  for (const callback of control.listeners.get('input') ?? []) callback({ target: control })
  await settle()
}
export async function click(control) {
  assert.ok(control, 'missing control')
  assert.ok(!control.props.disabled)
  control.props.onClick({ preventDefault() {} })
  await settle()
}
export function button(tree, label) {
  return find(tree, (n) => n.type === 'button' && contents(n) === label)[0]
}
export async function submit(form) {
  form.props.onSubmit({ preventDefault() {} })
  await settle()
}
