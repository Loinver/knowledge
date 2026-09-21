import { createI18n } from 'vue-i18n'

import enUS from '../locales/en-US.json'
import zhCN from '../locales/zh-CN.json'

const STORAGE_KEY = 'kg-locale'
const SUPPORTED = ['zh-CN', 'en-US'] as const
export type AppLocale = (typeof SUPPORTED)[number]

function detectLocale(): AppLocale {
  const stored = typeof localStorage !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null
  if (stored && SUPPORTED.includes(stored as AppLocale)) {
    return stored as AppLocale
  }
  const nav = typeof navigator !== 'undefined' ? navigator.language : 'zh-CN'
  if (nav.startsWith('zh')) return 'zh-CN'
  if (nav.startsWith('en')) return 'en-US'
  return 'zh-CN'
}

export const i18n = createI18n({
  legacy: false,
  locale: detectLocale(),
  fallbackLocale: 'zh-CN',
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS,
  },
})

export function setLocale(locale: AppLocale): void {
  i18n.global.locale.value = locale
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(STORAGE_KEY, locale)
  }
}

export function getLocale(): AppLocale {
  return i18n.global.locale.value as AppLocale
}
