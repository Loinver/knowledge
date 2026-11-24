import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

import { renderToString } from '@vue/server-renderer'
import { validate } from 'vee-validate'
import { createServer } from 'vite'
import { createSSRApp, h } from 'vue'
import { createI18n } from 'vue-i18n'

const root = fileURLToPath(new URL('../../../../../', import.meta.url))

function createPrimitiveServer() {
  return createServer({
    root,
    configFile: `${root}/vite.config.ts`,
    logLevel: 'error',
    server: { middlewareMode: true, hmr: false, ws: false, watch: null },
    optimizeDeps: { noDiscovery: true, include: [] },
    appType: 'custom',
  })
}

test('primitive defaults consume the project language packs without a second message source', async () => {
  const server = await createPrimitiveServer()
  try {
    const { usePrimitiveI18n } = await server.ssrLoadModule('/src/components/ui/utils.ts')
    const { Dialog, DialogFooter } = await server.ssrLoadModule(
      '/src/components/ui/primitives/dialog/index.ts',
    )
    const { Pagination, PaginationFirst, PaginationNext } = await server.ssrLoadModule(
      '/src/components/ui/primitives/pagination/index.ts',
    )
    for (const locale of ['zh-CN', 'en-US']) {
      const messages = JSON.parse(readFileSync(`${root}/src/locales/${locale}.json`, 'utf8'))
      const keys = ['close', 'first', 'last', 'next', 'previous', 'more']
      const values = keys.map((key) => messages.ds?.primitives?.[key])
      assert.ok(
        values.every((value) => typeof value === 'string'),
        `${locale}: ds.primitives keys`,
      )
      const expected = values.join('/')
      const originalMessages = structuredClone(messages)
      const i18n = createI18n({ legacy: false, locale, messages: { [locale]: messages } })
      const app = createSSRApp({
        setup() {
          const { t } = usePrimitiveI18n()
          return () =>
            h('span', ['close', 'first', 'last', 'next', 'previous', 'more'].map(t).join('/'))
        },
      }).use(i18n)
      assert.equal(await renderToString(app), `<span>${expected}</span>`)
      assert.deepEqual(i18n.global.getLocaleMessage(locale), originalMessages)
      const primitives = createSSRApp({
        setup() {
          return () =>
            h('section', [
              h(
                Dialog,
                { open: true },
                { default: () => h(DialogFooter, { showCloseButton: true }) },
              ),
              h(
                Pagination,
                { total: 100, itemsPerPage: 10 },
                { default: () => [h(PaginationFirst), h(PaginationNext)] },
              ),
            ])
        },
      }).use(i18n)
      const html = await renderToString(primitives)
      const [close, first, , next] = expected.split('/')
      assert.ok(html.includes(close), html)
      assert.ok(html.includes(`aria-label="${first}"`), html)
      assert.ok(html.includes(`aria-label="${next}"`), html)
    }
  } finally {
    await server.close()
  }
})

test('Reka 2.11 checked and active attributes match the adapted state selectors', async () => {
  const server = await createPrimitiveServer()
  try {
    const { Checkbox } = await server.ssrLoadModule(
      '/src/components/ui/primitives/checkbox/index.ts',
    )
    const { Switch } = await server.ssrLoadModule('/src/components/ui/primitives/switch/index.ts')
    const { Tabs, TabsList, TabsTrigger } = await server.ssrLoadModule(
      '/src/components/ui/primitives/tabs/index.ts',
    )
    const app = createSSRApp({
      setup() {
        return () =>
          h('section', [
            h(Checkbox, { modelValue: true }),
            h(Switch, { modelValue: true }),
            h(
              Tabs,
              { defaultValue: 'one' },
              {
                default: () =>
                  h(TabsList, null, { default: () => h(TabsTrigger, { value: 'one' }) }),
              },
            ),
          ])
      },
    })
    const html = await renderToString(app)
    assert.ok(html.includes('data-state="checked"'), html)
    assert.ok(html.includes('data-[state=checked]:'), html)
    assert.ok(html.includes('data-state="active"'), html)
    assert.ok(html.includes('data-[state=active]:'), html)
  } finally {
    await server.close()
  }
})

test('installed VeeValidate function rules preserve false and zero without a schema adapter', async () => {
  assert.equal((await validate(false, (value) => value === false || 'invalid')).valid, true)
  assert.equal((await validate(0, (value) => value === 0 || 'invalid')).valid, true)
  const invalid = await validate(null, (value) => value !== null || 'required')
  assert.equal(invalid.valid, false)
  assert.deepEqual(invalid.errors, ['required'])
})
