import { randomUUID } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { readFile, unlink, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { compileScript, parse, registerTS } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { build } from 'esbuild'
import {
  computed,
  createRenderer,
  createSSRApp,
  getCurrentInstance,
  h,
  nextTick,
  provide,
  shallowReactive,
} from 'vue'
import { createI18n } from 'vue-i18n'

const root = fileURLToPath(new URL('../../../../../', import.meta.url))
const resolvePackage = createRequire(path.join(root, 'web/package.json'))
registerTS(() => resolvePackage('typescript'))
const cache = new Map()
export async function load(entry, template = false) {
  const cacheKey = `${entry}:${template}`
  if (cache.has(cacheKey)) return cache.get(cacheKey)
  const filename = path.join(root, 'web/src/components/ui', entry)
  const id = randomUUID().replaceAll('-', '')
  const output = `/private/tmp/controls_${id}.mjs`
  const result = await build({
    entryPoints: [filename],
    bundle: true,
    platform: 'node',
    format: 'esm',
    write: false,
    plugins: [
      {
        name: 'controls-sfc',
        setup(builder) {
          builder.onResolve({ filter: /^@\// }, ({ path: value, kind, resolveDir }) =>
            builder.resolve(path.join(root, 'web/src', value.slice(2)), { kind, resolveDir }),
          )
          builder.onResolve({ filter: /^[^./]/ }, ({ path: value }) => ({
            path: resolvePackage.resolve(value),
            external: true,
          }))
          builder.onLoad({ filter: /\.vue$/ }, async ({ path: file }) => {
            const { descriptor } = parse(await readFile(file, 'utf8'), { filename: file })
            const contents = compileScript(descriptor, {
              id,
              inlineTemplate: template || file !== filename,
              fs: { fileExists: existsSync, readFile: (value) => readFileSync(value, 'utf8') },
            }).content
            return {
              contents:
                contents +
                (file === filename ? '\nexport { fieldContextKey } from "./formTypes"' : ''),
              loader: 'ts',
              resolveDir: path.dirname(file),
            }
          })
        },
      },
    ],
  })
  await writeFile(output, result.outputFiles[0].text)
  try {
    const module = await import(pathToFileURL(output).href)
    cache.set(
      cacheKey,
      entry.endsWith('.vue')
        ? Object.assign(module.default, { __fieldContextKey: module.fieldContextKey })
        : module,
    )
    return cache.get(cacheKey)
  } finally {
    await unlink(output)
  }
}
const renderer = createRenderer({
  createElement: () => ({}),
  createText: () => ({}),
  createComment: () => ({}),
  insert() {},
  remove() {},
  setText() {},
  setElementText() {},
  patchProp() {},
  parentNode: () => null,
  nextSibling: () => null,
})
const i18n = () =>
  createI18n({
    legacy: false,
    locale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages: {
      en: {
        ds: {
          clear: 'Clear',
          selectPlaceholder: 'Select',
          noOptions: 'No options',
          loading: 'Loading',
          dateRange: 'Range',
          startDate: 'Start',
          endDate: 'End',
          expand: 'Expand',
          collapse: 'Collapse',
          selectItem: 'Select item',
          showPassword: 'Show password',
          hidePassword: 'Hide password',
        },
      },
    },
  })

/** Exercise actual component handlers and Vue injection, without simulating Reka keyboard behavior. */
export async function control(entry, values = {}, fieldValues = {}, slots = {}) {
  const Component = await load(entry)
  const fieldContextKey = Component.__fieldContextKey
  const props = shallowReactive({ ...values })
  const validation = []
  let state
  const testComponent = {
    ...Component,
    render() {
      state = getCurrentInstance().setupState
      return null
    },
  }
  const field = {
    id: 'control-id',
    labelId: 'control-label',
    descriptionId: computed(() => 'control-help'),
    invalid: computed(() => true),
    required: computed(() => true),
    disabled: computed(() => Boolean(fieldValues.disabled)),
    readonly: computed(() => Boolean(fieldValues.readonly)),
    validate: (trigger) => validation.push(trigger),
  }
  // The key comes from the component bundle, preserving the actual injected context identity.
  const app = renderer.createApp({
    setup() {
      provide(fieldContextKey, field)
      return () => h(testComponent, props, slots)
    },
  })
  app.use(i18n())
  const vm = app.mount({})
  await nextTick()
  return {
    state,
    props,
    validation,
    vm,
    stop: () => app.unmount(),
    update: async (next) => {
      Object.assign(props, next)
      await nextTick()
    },
  }
}
export async function render(entry, props = {}, slots = {}) {
  const Component = await load(entry, true)
  const app = createSSRApp({ render: () => h(Component, props, slots) })
  app.use(i18n())
  return renderToString(app)
}
