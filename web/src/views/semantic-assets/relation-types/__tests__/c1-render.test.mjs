import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { test } from 'node:test'

import { renderToString } from '@vue/server-renderer'
import { createPinia } from 'pinia'
import { createSSRApp, h } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

import { load, root } from './c1-render-harness.mjs'

async function i18n(locale) {
  const messages = JSON.parse(
    await readFile(path.join(root, `web/src/locales/${locale}.json`), 'utf8'),
  )
  return createI18n({ legacy: false, locale, messages: { [locale]: messages } })
}

test('relation semantic controls render both endpoints, OWL and translated definitions with inherited disabled state', async () => {
  const { default: Fields, FormContainer } = await load(
    'views/semantic-assets/relation-types/components/RelationSemanticFields.vue',
  )
  for (const locale of ['en-US', 'zh-CN']) {
    const translation = await i18n(locale)
    const model = {
      definitionZh: '示例定义',
      definitionEn: 'Example definition',
      domainCardinality: { min: 0, max: 3 },
      rangeCardinality: { min: 1, max: -1 },
      inverseOf: 5,
      owl: { functional: false, inverse_functional: true, symmetric: false, transitive: false },
    }
    const html = await renderToString(
      createSSRApp({
        render: () =>
          h(FormContainer, { model, disabled: true }, () =>
            h(Fields, {
              ...model,
              inverseOptions: [{ value: 5, label: 'Inverse relation' }],
              referencesLoading: false,
            }),
          ),
      }).use(translation),
    )
    for (const key of [
      'domainCardinality',
      'rangeCardinality',
      'inverseOf',
      'functional',
      'inverseFunctional',
      'symmetric',
      'transitive',
    ])
      assert.ok(html.includes(translation.global.t(`relation.${key}`)), key)
    assert.match(html, /示例定义/)
    assert.match(html, /Example definition/)
    assert.match(html, /Inverse relation/)
    const numbers = html.match(/<input[^>]+type="number"[^>]*>/g) ?? []
    assert.equal(numbers.length, 4)
    assert.ok(numbers.every((input) => input.includes('disabled')))
    assert.equal(new Set(numbers.map((input) => input.match(/\bid="([^"]+)"/)[1])).size, 4)
    assert.ok(numbers.some((input) => /value="0"/.test(input)))
    const checkboxes = html.match(/<button[^>]+role="checkbox"[^>]*>/g) ?? []
    assert.equal(checkboxes.length, 4)
    assert.equal(new Set(checkboxes.map((checkbox) => checkbox.match(/\bid="([^"]+)"/)[1])).size, 4)
    assert.ok(checkboxes.every((checkbox) => checkbox.includes('disabled')))
    assert.equal(
      checkboxes.filter((checkbox) => checkbox.includes('aria-checked="false"')).length,
      3,
    )
  }
})

test('business domain table renders independent member IDs and the real fixed action column', async () => {
  const { default: Page } = await load(
    'views/semantic-assets/business-domains/BusinessDomainsPage.vue',
    `
    loading.value = false
    selected.value = {id: 1, name: 'Example', iri: 'urn:example:domain', label_i18n: {}, status: 'DRAFT', current_revision: 1, edit_revision: 2}
    members.value = [{id: 11, resource_id: 1, as_ref: false}, {id: 12, resource_id: 1, as_ref: true}]
    typeList.value = [{id: 1, name: 'Entity', iri: 'https://example.org/a/very/long/Entity', label_i18n: {}, status: 'PUBLISHED', current_revision: 1}]
  `,
  )
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: Page }],
  })
  await router.push('/')
  const html = await renderToString(
    createSSRApp(Page)
      .use(await i18n('en-US'))
      .use(createPinia())
      .use(router),
  )
  assert.match(html, /data-row-key="11"/)
  assert.match(html, /data-row-key="12"/)
  assert.match(html, /position:sticky;right:0px/)
  assert.match(html, /title="https:\/\/example.org\/a\/very\/long\/Entity"/)
  assert.doesNotMatch(html, /n-data-table/)
})

test('relation card read failure renders its retry without an empty-success state', async () => {
  const { default: Page } = await load(
    'views/semantic-assets/relation-types/RelationTypesPage.vue',
    `
    view.value = 'card'
    loading.value = false
    loadError.value = 'visible relation read failure'
  `,
  )
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: Page }],
  })
  await router.push('/')
  const translation = await i18n('en-US')
  const html = await renderToString(
    createSSRApp(Page).use(translation).use(createPinia()).use(router),
  )
  assert.match(html, /visible relation read failure/)
  assert.ok(html.includes(translation.global.t('ui.retry')))
  assert.doesNotMatch(html, /empty-card/)
})
