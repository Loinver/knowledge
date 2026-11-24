import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'

const root = path.resolve(import.meta.dirname, '../../../..')
const require = createRequire(path.join(root, 'web/package.json'))
const { build } = require('esbuild')

async function loadI18n() {
  const result = await build({
    entryPoints: [path.join(root, 'web/src/i18n/index.ts')],
    bundle: true,
    write: false,
    platform: 'node',
    format: 'esm',
    plugins: [
      {
        name: 'installed-vue-i18n',
        setup(builder) {
          builder.onResolve({ filter: /^[^./]/ }, ({ path: specifier }) => ({
            path: require.resolve(specifier),
            external: true,
          }))
        },
      },
    ],
  })
  const code = result.outputFiles[0].text.replace(
    /from "(\/[^"]+)"/g,
    (_, file) => `from ${JSON.stringify(pathToFileURL(file).href)}`,
  )
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
}

test('the actual locale entry visibly marks missing translations and preserves translated interpolation', async (t) => {
  const { i18n, setLocale, getLocale } = await loadI18n()
  const original = i18n.global.getLocaleMessage('en-US')
  t.after(() => i18n.global.setLocaleMessage('en-US', original))
  setLocale('en-US')
  assert.equal(getLocale(), 'en-US')
  assert.equal(i18n.global.t('common.close'), 'Close')
  assert.match(i18n.global.t('ds.form.maxLength', { max: 7 }), /7 characters/)
  const missing = structuredClone(original)
  delete missing.common.close
  i18n.global.setLocaleMessage('en-US', missing)
  assert.equal(i18n.global.t('common.close'), 'Not translated · common.close')
  assert.equal(i18n.global.t('unknown.contract'), 'Not translated · unknown.contract')
  setLocale('zh-CN')
  assert.equal(i18n.global.t('common.close'), '关闭')
  assert.equal(i18n.global.t('unknown.contract'), '未翻译 · unknown.contract')
  setLocale('en-US')
  i18n.global.setLocaleMessage('en-US', original)
  assert.equal(i18n.global.t('common.close'), 'Close')
})
