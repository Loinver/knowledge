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
import { createRenderer, h, nextTick, reactive, shallowRef } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'

const web = fileURLToPath(new URL('../../../..', import.meta.url))
const resolvePackage = createRequire(path.join(web, 'package.json'))
registerTS(() => resolvePackage('typescript'))
globalThis.Document ??= class {}
globalThis.ShadowRoot ??= class {}
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
export const find = (tree, predicate) =>
  [tree, ...tree.children.flatMap((child) => find(child, predicate))].filter(predicate)
export const contents = (tree) =>
  (tree.type === '#comment' ? '' : tree.text) + tree.children.map(contents).join('')
function node(type, text = '') {
  return {
    __v_skip: true,
    type,
    tagName: type.toUpperCase(),
    text,
    props: {},
    children: [],
    parent: null,
    getRootNode() {
      return this.parent?.getRootNode() ?? this
    },
    focus() {
      this.getRootNode().activeElement = this
    },
    scrollIntoView() {},
    getAttribute(name) {
      return this.props[name] ?? null
    },
    querySelector(selector) {
      return find(this, (item) => selector.split(',').includes(item.type))[0] ?? null
    },
    addEventListener() {},
    removeEventListener() {},
  }
}
const renderer = createRenderer({
  createElement: node,
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
  patchProp(item, key, _old, value) {
    item.props[key] = value
  },
})
async function compile(entryName, api, session) {
  const entry = path.join(web, 'src/views/knowledge/components', entryName)
  const key = `c4_drawer_${randomUUID()}`
  const output = `/private/tmp/${key}.mjs`
  globalThis[key] = { api, session }
  const exposes = {
    'DocumentDrawer.vue': 'act,busy,actionError,reload,loading',
    'EvidenceDrawer.vue': 'linkForm,reload,loading,error,close',
    'GraphLinkForm.vue':
      'confirmClose,open,query,graph,entity,fact,save,busy,error,canSave,documents',
  }
  try {
    const result = await build({
      entryPoints: [entry],
      write: false,
      bundle: true,
      platform: 'node',
      format: 'esm',
      logLevel: 'silent',
      loader: { '.css': 'empty' },
      plugins: [
        {
          name: 'c4-drawer-real-templates',
          setup(builder) {
            builder.onResolve(
              { filter: /^@\/api\/(knowledge|graph|tokens|auth)$/ },
              ({ path: value }) => ({ path: value, namespace: 'fixture' }),
            )
            builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path: value }) => ({
              contents: value.endsWith('/tokens')
                ? `const session=globalThis[${JSON.stringify(key)}].session; export const getSessionGeneration=()=>session.generation; export const subscribeTokens=listener=>{session.listeners.add(listener);return()=>session.listeners.delete(listener)}; export const hasSession=()=>true; export const getAccessToken=()=> 'fixture'; export const clearTokens=()=>{}; export const storeTokens=()=>true;`
                : `export const ${value.split('/').at(-1)}Api = globalThis[${JSON.stringify(key)}].api[${JSON.stringify(value.split('/').at(-1))}] ?? {}`,
            }))
            builder.onResolve({ filter: /^@\// }, ({ path: value, kind, resolveDir }) =>
              builder.resolve(path.join(web, 'src', value.slice(2)), { kind, resolveDir }),
            )
            builder.onResolve({ filter: /^[^./]/ }, async ({ path: value, pluginData }) => {
              if (pluginData?.externalize) return undefined
              const resolved = await builder.resolve(value, {
                kind: 'import-statement',
                resolveDir: web,
                pluginData: { externalize: true },
              })
              if (resolved.errors.length) return { errors: resolved.errors }
              return { path: resolved.path, external: true }
            })
            builder.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
              // Only DOM-dependent overlays/selects are substitutes. Parent/child v-if/key,
              // form validation, draft guards, SearchPanel and the router use production code.
              if (filename.endsWith('/UiDrawer.vue'))
                return {
                  contents: `import {h} from 'vue';export default {props:['show'],setup(p,{slots}){return()=>p.show?h('section',{},slots.default?.()):null}}`,
                }
              if (filename.endsWith('/UiDrawerContent.vue'))
                return {
                  contents: `import {h} from 'vue';export default {setup(p,{slots}){return()=>h('section',{},[slots.default?.(),slots.footer?.()])}}`,
                }
              if (filename.endsWith('/UiPopconfirm.vue'))
                return {
                  contents: `import {h} from 'vue';export default {setup(p,{slots}){return()=>h('div',{},slots.trigger?.())}}`,
                }
              if (filename.endsWith('/UiSelect.vue'))
                return {
                  contents: `import {h,inject} from 'vue';import {fieldContextKey} from '@/components/ui/formTypes';export default {props:['value','options','disabled'],setup(p){const field=inject(fieldContextKey,undefined);return()=>h('select',{value:p.value,disabled:p.disabled||field?.disabled.value},p.options?.map(o=>h('option',{value:o.value},o.label)))}}`,
                  resolveDir: path.dirname(filename),
                }
              let source = await readFile(filename, 'utf8')
              const expose = exposes[path.basename(filename)]
              if (expose)
                source = source
                  .replace(/defineExpose\(\{[^}]*\}\)/g, '')
                  .replace('</script>', `\ndefineExpose({${expose}})\n</script>`)
              const { descriptor } = parse(source, { filename })
              const id = `${key}-${filename}`
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
    await writeFile(output, result.outputFiles[0].text)
    return {
      component: (await import(pathToFileURL(output).href)).default,
      cleanup: () => delete globalThis[key],
    }
  } catch (error) {
    delete globalThis[key]
    throw error
  } finally {
    await unlink(output).catch(() => {})
  }
}

export async function mountDrawer(t, entry, api, query = '?evidence=c1') {
  const session = { generation: 'first', listeners: new Set() }
  const built = await compile(entry, api, session)
  const i18n = createI18n({
    legacy: false,
    locale: 'en-US',
    messages: {
      'en-US': JSON.parse(await readFile(path.join(web, 'src/locales/en-US.json'), 'utf8')),
    },
  })
  const pinia = createPinia()
  pinia.state.value.auth = {
    user: { id: 1, role: 'EDITOR', status: 'ACTIVE', username: 'fixture' },
  }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/knowledge-bases/:id', component: built.component },
      { path: '/away', component: { render: () => h('div', {}, 'away') } },
    ],
  })
  await router.push(`/knowledge-bases/1${query}`)
  const props = reactive({ kbId: 1, baseArchived: false })
  const vm = shallowRef()
  let changed = 0
  const tree = node('root')
  const app = renderer
    .createApp({
      render: () =>
        h(
          RouterView,
          {},
          {
            default: ({ Component }) =>
              h(Component, { ...props, ref: vm, onChanged: () => changed++ }),
          },
        ),
    })
    .use(router)
    .use(i18n)
    .use(pinia)
  app.mount(tree)
  let stopped = false
  const stop = () => {
    if (stopped) return
    stopped = true
    app.unmount()
    pinia._s.forEach((store) => store.$dispose())
    built.cleanup()
  }
  t.after(stop)
  await settle()
  return {
    get vm() {
      return vm.value
    },
    get user() {
      return pinia.state.value.auth.user
    },
    set user(value) {
      pinia.state.value.auth.user = value
    },
    tree,
    props,
    router,
    stop,
    changed: () => changed,
    rotateSession() {
      session.generation += '-next'
      for (const listener of session.listeners) listener()
    },
    refreshTokens() {
      for (const listener of session.listeners) listener()
    },
  }
}
