import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { readFile, unlink, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { compileScript, compileTemplate, parse, registerTS } from '@vue/compiler-sfc'
import { build } from 'esbuild'
import { createPinia } from 'pinia'
import { createRenderer } from 'vue'
import { createI18n } from 'vue-i18n'

import { deferred, settle } from './configuration-harness.mjs'

const web = fileURLToPath(new URL('../../../../..', import.meta.url))
const resolvePackage = createRequire(path.join(web, 'package.json'))
registerTS(() => resolvePackage('typescript'))
globalThis.Document ??= class {}
globalThis.ShadowRoot ??= class {}

// Pending locale additions are test-only; the coordinating agent integrates the real JSON keys.
const additions = {
  'en-US': {
    entriesRequired: 'Add at least one enum value.',
    valueDuplicate: 'Machine values must be unique after trimming spaces.',
  },
  'zh-CN': {
    entriesRequired: '请至少添加一个枚举值。',
    valueDuplicate: '去除首尾空格后，机读值不能重复。',
  },
}
const dictionary = (id = 1, revision = 3) => ({
  id,
  revision,
  name: `Status${id}`,
  label_i18n: { 'zh-CN': '状态', 'en-US': 'Status' },
  definition_i18n: { 'zh-CN': '状态定义', 'en-US': 'Status definition' },
  entries: [{ value: 'OPEN', label_i18n: { 'zh-CN': '开放', 'en-US': 'Open' } }],
})

function find(tree, predicate) {
  return [tree, ...tree.children.flatMap((child) => find(child, predicate))].filter(predicate)
}
function contents(tree) {
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

async function compile(api) {
  const entry = path.join(
    web,
    'src/views/semantic-assets/configuration/enum-dictionaries/EnumDictionariesPage.vue',
  )
  const key = `dictionary_form_${randomUUID()}`
  const outfile = `/private/tmp/${key}.mjs`
  globalThis[key] = api
  try {
    const result = await build({
      entryPoints: [entry],
      outfile,
      write: false,
      bundle: true,
      platform: 'node',
      format: 'esm',
      logLevel: 'silent',
      plugins: [
        {
          name: 'dictionary-real-form',
          setup(builder) {
            builder.onResolve(
              { filter: /^(vue-router|@\/api\/enum-dictionaries)$/ },
              ({ path: value }) => ({ path: value, namespace: 'stub' }),
            )
            builder.onLoad({ filter: /.*/, namespace: 'stub' }, ({ path: value }) => ({
              contents:
                value === 'vue-router'
                  ? `export const useRoute = () => ({query: {}, params: {}}); export const useRouter = () => ({replace(){}}); export const onBeforeRouteLeave = () => {}`
                  : `export const enumDictionariesApi = globalThis[${JSON.stringify(key)}]`,
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
              let source = await readFile(filename, 'utf8')
              if (filename === entry) {
                // Keep the exact page form and footer consumer markup. Only the drawer/tabs shell
                // is excluded: this renderer tests real Form/Field/Input, not Reka browser behavior.
                const form = source.match(/<FormContainer\s[\s\S]*?<\/FormContainer\s*>/)[0]
                const footer = source.match(/<template #footer>([\s\S]*?)<\/template>/)[1]
                source = source
                  .replace(
                    /<template>[\s\S]*?<\/template>\s*<style/,
                    `<template><div v-if="showEditor && activeTab === 'edit'">${form}${footer}</div></template><style`,
                  )
                  .replace(
                    '</script>',
                    '\ndefineExpose({form,formRef,rules,busy,validating,saved,showEditor,editorError,editorReady,activeTab,openCreate,openEdit,submit})\n</script>',
                  )
              }
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

async function mount({ locale = 'en-US', role = 'EDITOR', ...overrides } = {}) {
  const writes = []
  const api = {
    list: async () => ({ items: [], total: 0 }),
    get: async (id) => dictionary(id),
    revisions: async (id) => [dictionary(id)],
    references: async () => [],
    create: async (input) => writes.push({ input: structuredClone(input) }),
    update: async (item, input) => writes.push({ item, input: structuredClone(input) }),
    ...overrides,
  }
  const built = await compile(api)
  const messages = {}
  for (const language of ['en-US', 'zh-CN']) {
    messages[language] = JSON.parse(await readFile(path.join(web, `src/locales/${language}.json`)))
    Object.assign(messages[language].enumDictionaries, additions[language])
  }
  const i18n = createI18n({ legacy: false, locale, messages })
  const pinia = createPinia()
  pinia.state.value.auth = { user: { id: 1, role, status: 'ACTIVE' } }
  const tree = node('root')
  const app = renderer.createApp(built.component).use(i18n).use(pinia)
  const vm = app.mount(tree)
  await settle()
  return {
    vm,
    tree,
    i18n,
    writes,
    controls: () => find(tree, (item) => item.type === 'input' || item.type === 'textarea'),
    invalid: () => find(tree, (item) => item.props['aria-invalid']),
    stop() {
      app.unmount()
      built.cleanup()
    },
  }
}

async function input(control, value) {
  assert.ok(!control.props.disabled)
  control.value = value
  control.props.onInput?.({ target: control })
  for (const callback of control.listeners.get('input') ?? []) callback({ target: control })
  await settle()
}
async function click(button) {
  assert.ok(!button.props.disabled)
  button.props.onClick({ preventDefault() {} })
  await settle()
}
function button(view, text) {
  return find(view.tree, (item) => item.type === 'button' && contents(item) === text)[0]
}
function description(view, control) {
  const id = control.props['aria-describedby']
  const result = find(view.tree, (item) => item.props.id === id)[0]
  assert.ok(result, `Missing error description for ${id}`)
  const label = find(view.tree, (item) => item.props.id === control.props['aria-labelledby'])[0]
  assert.equal(label.props.for, control.props.id)
  return contents(result)
}

test('test_dictionary_empty_save_uses_real_field_errors_and_focus_in_both_locales', async () => {
  for (const locale of ['en-US', 'zh-CN']) {
    const view = await mount({ locale })
    try {
      view.vm.openCreate()
      await settle()
      await click(button(view, view.i18n.global.t('common.save')))
      const controls = view.controls()
      assert.equal(view.writes.length, 0)
      assert.equal(view.vm.showEditor, true)
      assert.equal(view.vm.editorError, '')
      assert.equal(view.invalid().length, 5)
      assert.equal(view.tree.activeElement, controls[0])
      for (const control of view.invalid()) {
        assert.equal(description(view, control), view.i18n.global.t('common.required'))
      }
      await input(controls[0], 'Status')
      assert.equal(controls[0].props['aria-invalid'], undefined)
      assert.equal(controls[0].props['aria-describedby'], undefined)
      assert.equal(view.invalid().length, 4)
    } finally {
      view.stop()
    }
  }
})

test('test_dictionary_definition_only_error_and_native_submit_format_focus', async () => {
  const view = await mount()
  try {
    await view.vm.openEdit(dictionary())
    await settle()
    const controls = view.controls()
    assert.equal(controls[3].type, 'textarea')
    await input(controls[3], '   ')
    assert.equal(view.vm.form.definition_i18n['zh-CN'], '   ')
    const form = find(view.tree, (item) => item.type === 'form')[0]
    await form.props.onSubmit({ preventDefault() {} })
    await settle()
    assert.equal(view.writes.length, 0)
    assert.deepEqual(
      view.invalid().map((control) => control.props.id),
      [controls[3].props.id],
    )
    assert.equal(view.tree.activeElement, controls[3])
    assert.equal(description(view, controls[3]), view.i18n.global.t('common.required'))
    assert.equal(view.vm.form.definition_i18n['zh-CN'], '   ')
    view.vm.openCreate()
    await settle()
    await input(view.controls()[0], 'bad-name')
    assert.deepEqual(
      view.invalid().map((control) => control.props.id),
      [view.controls()[0].props.id],
    )
    assert.equal(description(view, view.controls()[0]), view.i18n.global.t('ontology.namePattern'))
  } finally {
    view.stop()
  }
})

test('test_dictionary_duplicate_rows_recheck_on_fix_delete_and_locale_without_touching_blank_rows', async () => {
  const view = await mount()
  try {
    await view.vm.openEdit(dictionary())
    await settle()
    await click(button(view, view.i18n.global.t('enumDictionaries.addEntry')))
    await input(view.controls()[8], ' OPEN ')
    await input(view.controls()[9], '第二项')
    await view.vm.submit()
    await settle()
    assert.equal(view.writes.length, 0)
    const first = view.controls()[5]
    const second = view.controls()[8]
    assert.deepEqual(
      view.invalid().map((control) => control.props.id),
      [first.props.id, second.props.id],
    )
    assert.equal(view.tree.activeElement, first)
    assert.equal(description(view, first), additions['en-US'].valueDuplicate)
    assert.equal(description(view, second), additions['en-US'].valueDuplicate)
    view.i18n.global.locale.value = 'zh-CN'
    await settle()
    assert.equal(description(view, first), additions['zh-CN'].valueDuplicate)
    await input(first, 'CLOSED')
    assert.equal(view.invalid().length, 0)
    assert.equal(first.props['aria-describedby'], undefined)
    assert.equal(second.props['aria-describedby'], undefined)
    await input(first, 'OPEN')
    await view.vm.submit()
    await settle()
    assert.equal(view.invalid().length, 2)
    await input(second, 'CLOSED')
    assert.equal(view.invalid().length, 0)
    await input(second, ' OPEN ')
    await view.vm.submit()
    await settle()
    const remove = find(
      view.tree,
      (item) =>
        item.type === 'button' &&
        item.props['aria-label'] ===
          view.i18n.global.t('enumDictionaries.removeEntry', { index: 1 }),
    )[0]
    await click(remove)
    assert.equal(view.vm.form.entries.length, 1)
    assert.equal(view.vm.form.entries[0].value, ' OPEN ')
    assert.equal(view.invalid().length, 0)
    assert.equal(view.controls()[5].props['aria-describedby'], undefined)
    await click(button(view, view.i18n.global.t('enumDictionaries.addEntry')))
    assert.equal(view.invalid().length, 0)
    assert.equal(view.controls()[0].props.disabled, true)
  } finally {
    view.stop()
  }
})

test('test_dictionary_remaps_invalid_rows_after_deleting_an_unrelated_preceding_entry', async () => {
  for (const values of [
    ['A', ' B ', 'B'],
    ['B', 'A', ' B '],
  ]) {
    const view = await mount()
    try {
      const item = dictionary()
      item.entries = values.map((value) => ({
        value,
        label_i18n: { 'zh-CN': value, 'en-US': value },
      }))
      await view.vm.openEdit(item)
      await settle()
      // Use the opened current draft; the API fixture supplies the original dictionary.
      view.vm.form.entries = item.entries
      await settle()
      await view.vm.submit()
      await settle()
      assert.equal(view.invalid().length, 2)
      const index = values.indexOf('A')
      const remove = find(
        view.tree,
        (item) =>
          item.type === 'button' &&
          item.props['aria-label'] ===
            view.i18n.global.t('enumDictionaries.removeEntry', { index: index + 1 }),
      )[0]
      await click(remove)
      await settle()
      assert.equal(view.vm.form.entries.length, 2)
      assert.equal(view.invalid().length, 2)
      const first = view.controls()[5]
      const second = view.controls()[8]
      assert.deepEqual(
        view.invalid().map((control) => control.props.id),
        [first.props.id, second.props.id],
      )
      assert.equal(view.tree.activeElement, first)
      assert.equal(description(view, first), additions['en-US'].valueDuplicate)
      assert.equal(description(view, second), additions['en-US'].valueDuplicate)
      await input(second, 'Unique')
      assert.equal(view.invalid().length, 0)
      assert.equal(view.writes.length, 0)
    } finally {
      view.stop()
    }
  }
})

test('test_dictionary_zero_entries_focus_add_button_and_clear_existing_error_on_add', async () => {
  const view = await mount()
  try {
    await view.vm.openEdit(dictionary())
    await settle()
    view.vm.form.entries.splice(0)
    await settle()
    await view.vm.submit()
    await settle()
    assert.equal(view.writes.length, 0)
    assert.match(contents(view.tree), /Add at least one enum value/)
    const add = button(view, view.i18n.global.t('enumDictionaries.addEntry'))
    assert.equal(view.tree.activeElement, add)
    await click(add)
    assert.doesNotMatch(contents(view.tree), /Add at least one enum value/)
    assert.equal(view.invalid().length, 0)
  } finally {
    view.stop()
  }
})

test('test_dictionary_validation_and_write_locks_preserve_revision_raw_strings_and_failed_draft', async () => {
  const response = deferred()
  const writes = []
  const view = await mount({
    update: (item, payload) => {
      writes.push({ item, payload })
      return response.promise
    },
  })
  try {
    await view.vm.openEdit(dictionary(4, 9))
    await settle()
    await input(view.controls()[5], ' OPEN ')
    await input(view.controls()[1], ' 状态 ')
    const pending = view.vm.submit()
    assert.equal(view.vm.validating, true)
    await view.vm.submit()
    view.vm.openCreate()
    await view.vm.openEdit(dictionary(99))
    assert.equal(view.vm.saved.id, 4)
    await settle()
    assert.equal(writes.length, 1)
    assert.equal(writes[0].item.id, 4)
    assert.equal(writes[0].item.revision, 3)
    assert.equal(writes[0].payload.entries[0].value, ' OPEN ')
    assert.equal(writes[0].payload.label_i18n['zh-CN'], ' 状态 ')
    response.reject({ code: 'KG.REVISION_CONFLICT' })
    await pending
    await settle()
    assert.equal(view.vm.busy, false)
    assert.equal(view.vm.showEditor, true)
    assert.equal(view.vm.form.entries[0].value, ' OPEN ')
    assert.match(view.vm.editorError, /Close and reopen/)
  } finally {
    view.stop()
  }
})

test('test_dictionary_pending_validation_cannot_write_after_close_tab_or_model_replacement', async () => {
  for (const change of ['close', 'tab', 'model']) {
    const view = await mount()
    try {
      await view.vm.openEdit(dictionary())
      await settle()
      const pending = view.vm.submit()
      if (change === 'close') view.vm.showEditor = false
      if (change === 'tab') view.vm.activeTab = 'history'
      if (change === 'model') view.vm.form = dictionary(99)
      await pending
      await settle()
      assert.equal(view.writes.length, 0)
      assert.equal(view.vm.busy, false)
    } finally {
      view.stop()
    }
  }
})

test('test_dictionary_viewer_and_history_cannot_submit_or_mutate_controls', async () => {
  const view = await mount({ role: 'VIEWER' })
  try {
    view.vm.openCreate()
    assert.equal(view.vm.showEditor, false)
    await view.vm.openEdit(dictionary())
    await settle()
    assert.ok(view.controls().every((control) => control.props.disabled && control.props.readonly))
    await view.vm.submit()
    assert.equal(view.writes.length, 0)
    view.vm.activeTab = 'history'
    await view.vm.submit()
    assert.equal(view.writes.length, 0)
  } finally {
    view.stop()
  }
})
