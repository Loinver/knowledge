import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { test } from 'node:test'

import { renderToString } from '@vue/server-renderer'
import { createPinia } from 'pinia'
import { createSSRApp } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

import { load, root } from './c4-render-harness.mjs'

test('real knowledge advanced controls expose translated labels, help association and numeric zero', async () => {
  const { default: Page } = await load(
    'views/knowledge/KnowledgeSearchPage.vue',
    `
    base.cancel()
    capabilities.cancel()
    cancel()
    expanded.value = true
    threshold.value = 0
  `,
  )
  for (const locale of ['en-US', 'zh-CN']) {
    const messages = JSON.parse(
      await readFile(path.join(root, `web/src/locales/${locale}.json`), 'utf8'),
    )
    const translation = createI18n({ legacy: false, locale, messages: { [locale]: messages } })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/knowledge-bases/:id/search', name: 'knowledge-base-search', component: Page },
        {
          path: '/knowledge-bases/:id',
          name: 'knowledge-base-detail',
          component: { render: () => null },
        },
      ],
    })
    await router.push('/knowledge-bases/1/search')
    const html = await renderToString(
      createSSRApp(Page).use(translation).use(createPinia()).use(router),
    )
    const control = html.match(/<input[^>]+type="number"[^>]*>/)?.[0]
    assert.ok(control)
    assert.match(control, /value="0"/)
    const id = control.match(/\bid="([^"]+)"/)[1]
    const help = control.match(/aria-describedby="([^"]+)"/)[1]
    assert.ok(html.includes(`for="${id}"`))
    assert.ok(html.includes(`id="${help}"`))
    assert.ok(html.includes(translation.global.t('kb.minSimilarity')))
    assert.ok(html.includes(translation.global.t('kb.scoreExplanation')))
    assert.match(html, /aria-expanded="true"/)
    assert.doesNotMatch(html, /n-input|n-select/)
  }
})
