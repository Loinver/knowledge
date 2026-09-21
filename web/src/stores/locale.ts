import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { type AppLocale,getLocale, setLocale } from '@/i18n'

export const useLocaleStore = defineStore('locale', () => {
  const current = ref<AppLocale>(getLocale())

  const label = computed(() => (current.value === 'zh-CN' ? '中文' : 'EN'))

  function change(locale: AppLocale) {
    setLocale(locale)
    current.value = locale
  }

  return { current, label, change }
})
