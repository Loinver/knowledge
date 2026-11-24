import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '..')
const zh = JSON.parse(readFileSync(resolve(root, 'web/src/locales/zh-CN.json'), 'utf8'))
const en = JSON.parse(readFileSync(resolve(root, 'web/src/locales/en-US.json'), 'utf8'))

function collectKeys(obj, prefix = '') {
  const keys = []
  for (const [k, v] of Object.entries(obj)) {
    const full = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      keys.push(...collectKeys(v, full))
    } else {
      keys.push(full)
    }
  }
  return keys
}

const zhKeys = new Set(collectKeys(zh))
const enKeys = new Set(collectKeys(en))

const missingInEn = [...zhKeys].filter((k) => !enKeys.has(k))
const missingInZh = [...enKeys].filter((k) => !zhKeys.has(k))

if (missingInEn.length === 0 && missingInZh.length === 0) {
  console.log(`i18n keys OK: ${zhKeys.size} keys in both locales`)
  process.exit(0)
}

if (missingInEn.length > 0) {
  console.error('Missing in en-US:')
  for (const k of missingInEn) console.error('  - ' + k)
}
if (missingInZh.length > 0) {
  console.error('Missing in zh-CN:')
  for (const k of missingInZh) console.error('  - ' + k)
}
process.exit(1)
