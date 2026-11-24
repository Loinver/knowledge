import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { test } from 'node:test'

import { parse } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { createPinia } from 'pinia'
import { createRenderer, createSSRApp, h } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

import { load, root } from './mapping-render-harness.mjs'

async function translation(locale) {
  const messages = JSON.parse(
    await readFile(path.join(root, `web/src/locales/${locale}.json`), 'utf8'),
  )
  return createI18n({ legacy: false, locale, messages: { [locale]: messages } })
}
const entity = {
  localId: 1,
  entity_type: 'Employee',
  schema: 'main',
  table: 'employees',
  field_maps: [
    {
      target_attr: 'name',
      source_field: 'name',
      transform: 'IDENTITY',
      null_policy: 'SKIP',
      default_value: null,
    },
  ],
  key_fields: ['id'],
  incremental_field: null,
  match_keys: ['id'],
  fusion: { priority: 1, null_policy: 'KEEP', conflict_policy: 'PRIORITY' },
}
async function page(seed, locale) {
  const { default: Page } = await load(
    'views/data-integration/mapping/MappingWorkbenchPage.vue',
    seed,
  )
  const pinia = createPinia()
  pinia.state.value.auth = { user: { id: 1, role: 'EDITOR' } }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: Page }],
  })
  await router.push('/')
  return renderToString(
    createSSRApp(Page)
      .use(pinia)
      .use(await translation(locale))
      .use(router),
  )
}

test('real mapping controls render labelled checkbox values, field paths, fusion and the preserved SVG', async () => {
  const seed = `
    step.value = 3
    viewMode.value = 'graph'
    mappingName.value = 'Mapping1'
    selectedOntologyId.value = 1
    selectedDatasourceId.value = 1
    entityTypes.value = [{name:'Employee', iri:'urn:example:Employee', data_props:[{name:'name'}]}]
    catalog.value = {schemas:[{schema:'main',tables:[{name:'employees',columns:[{name:'id',type:'INT',primary_key:true},{name:'name',type:'TEXT',primary_key:false}]}]}]}
    entityMaps.value = ${JSON.stringify([entity])}
  `
  for (const locale of ['en-US', 'zh-CN']) {
    const html = await page(seed, locale)
    assert.match(html, /<svg[^>]*class="flow-arrow"/)
    assert.match(html, /data-testid="field-source"/)
    assert.match(html, /data-testid="fusion-priority"/)
    const checkboxes = html.match(/<button[^>]+role="checkbox"[^>]*>/g) ?? []
    assert.equal(checkboxes.length, 4)
    assert.equal(new Set(checkboxes.map((button) => button.match(/\bid="([^"]+)"/)[1])).size, 4)
    assert.equal(checkboxes.filter((button) => button.includes('aria-checked="true"')).length, 2)
    assert.equal(checkboxes.filter((button) => button.includes('aria-checked="false"')).length, 2)
    assert.ok(checkboxes.every((button) => button.includes('aria-label=')))
    assert.doesNotMatch(html, /<input[^>]+type="checkbox"|n-select|n-input/)
  }
})

test('real sample table renders 0 false null, a single search form and truncation context', async () => {
  const rendered = await page(
    `
    step.value = 2
    selectedDatasourceId.value = 1
    catalog.value = {schemas:[]}
    samplePreview.value = {columns:[{name:'value'}], rows:[{value:0},{value:false},{value:null}], truncated:true}
  `,
    'en-US',
  )
  const html = rendered.replace(/<!--[\s\S]*?-->/g, '')
  const cells = [...html.matchAll(/<td[^>]*>(.*?)<\/td>/g)].map((match) =>
    match[1].replace(/<[^>]+>/g, '').trim(),
  )
  assert.deepEqual(cells, ['0', 'false', 'NULL'])
  assert.equal((html.match(/type="search"/g) ?? []).length, 1)
  assert.match(html, /The sample reached the row limit/)
  assert.doesNotMatch(html, /<form[^>]*>(?:(?!<\/form>)[\s\S])*<form/)
})

test('empty entity mapping field contains the enabled add button as its first focus target', async () => {
  const html = await page(
    `
    step.value = 3
    mappingName.value = 'Mapping1'
    selectedOntologyId.value = 1
    selectedDatasourceId.value = 1
    entityTypes.value = [{name:'Employee', iri:'urn:Employee', data_props:[{name:'name'}]}]
    entityMaps.value = []
  `,
    'en-US',
  )
  // Inspect the actual page and Ui controls rendered by the existing SFC harness.
  const { descriptor, errors } = parse(`<template>${html}</template>`)
  assert.deepEqual(errors, [])
  const elements = (node) =>
    (node.children ?? []).flatMap((child) => (child.type === 1 ? [child, ...elements(child)] : []))
  const attribute = (node, name) => node.props.find((prop) => prop.name === name)
  const value = (node, name) => attribute(node, name)?.value?.content
  const nodes = elements(descriptor.template.ast)
  const fields = nodes.filter((node) => {
    const classes = value(node, 'class')?.split(/\s+/) ?? []
    return classes.includes('ui-field') && classes.includes('editors')
  })
  assert.equal(fields.length, 1)
  const addButtons = nodes.filter((node) => value(node, 'data-testid') === 'add-entity-mapping')
  assert.equal(addButtons.length, 1)
  // Mirrors FormContainer's descendant selector, including tabindex candidates.
  const focusTargets = elements(fields[0]).filter(
    (node) =>
      ['input', 'textarea', 'select', 'button'].includes(node.tag) || attribute(node, 'tabindex'),
  )
  assert.equal(focusTargets[0], addButtons[0])
  assert.equal(addButtons[0].tag, 'button')
  assert.equal(value(addButtons[0], 'type'), 'button')
  assert.equal(attribute(addButtons[0], 'disabled'), undefined)
  assert.notEqual(value(addButtons[0], 'tabindex'), '-1')
})

test('frozen detail renders only the supplied revision and preserves false zero null display', async () => {
  const { default: Frozen } = await load(
    'views/data-integration/mapping/components/FrozenMapping.vue',
  )
  const html = await renderToString(
    createSSRApp({
      render: () =>
        h(Frozen, {
          revision: {
            entity_maps: [
              {
                ...entity,
                field_maps: [
                  {
                    target_attr: 'zero',
                    source_field: 'zero',
                    transform: 'IDENTITY',
                    null_policy: 'SKIP',
                    default_value: 0,
                  },
                  {
                    target_attr: 'false',
                    source_field: 'false',
                    transform: 'IDENTITY',
                    null_policy: 'SKIP',
                    default_value: false,
                  },
                  {
                    target_attr: 'null',
                    source_field: 'null',
                    transform: 'IDENTITY',
                    null_policy: 'SKIP',
                    default_value: null,
                  },
                ],
              },
            ],
            rel_maps: [],
          },
        }),
    }).use(await translation('en-US')),
  )
  assert.match(html, />0<\/td>/)
  assert.match(html, />false<\/td>/)
  assert.match(html, />—<\/td>/)
  assert.doesNotMatch(html, /newUpstreamField/)
})

test('real FormContainer invalid submission focuses the registered field and emits no submit', async () => {
  const { FormContainer, FormField } = await load(
    'views/data-integration/mapping/components/FrozenMapping.vue',
    '',
    false,
  )
  let focused = ''
  let submits = 0
  const renderer = createRenderer({
    createElement: (tag) => ({
      tag,
      children: [],
      attrs: {},
      focus() {
        focused = this.attrs.id
      },
      querySelector() {
        const walk = (node) =>
          ['input', 'button', 'textarea', 'select'].includes(node.tag)
            ? node
            : node.children.map(walk).find(Boolean)
        return this.children.map(walk).find(Boolean)
      },
    }),
    createText: () => ({ children: [] }),
    createComment: () => ({ children: [] }),
    setText() {},
    setElementText() {},
    parentNode: (element) => element.parent,
    nextSibling: () => null,
    insert: (element, parent) => {
      element.parent = parent
      parent.children.push(element)
    },
    remove: (element) => {
      if (element.parent)
        element.parent.children = element.parent.children.filter((child) => child !== element)
    },
    patchProp: (element, key, _before, value) => {
      element.attrs[key] = value
    },
  })
  let form
  const app = renderer
    .createApp({
      render: () =>
        h(
          FormContainer,
          {
            ref: (value) => {
              form = value
            },
            model: { entityMaps: [{ name: '' }] },
            rules: { 'entityMaps.0.name': { required: true } },
            onSubmit: () => submits++,
          },
          () =>
            h(
              FormField,
              { path: 'entityMaps.0.name', label: 'Name' },
              {
                default: (field) => h('input', { id: field.id, value: '' }),
              },
            ),
        ),
    })
    .use(await translation('en-US'))
  const container = { children: [] }
  app.mount(container)
  try {
    const formElement = container.children.find((node) => node.tag === 'form')
    await formElement.attrs.onSubmit({ preventDefault() {} })
    assert.ok(focused)
    assert.equal(submits, 0)
    await assert.rejects(form.validate(), /FORM_INVALID/)
  } finally {
    app.unmount()
  }
})
