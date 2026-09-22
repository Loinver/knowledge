import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { type AppLocale, getLocale, setLocale } from '@/i18n'

export const useLocaleStore = defineStore('locale', () => {
  const current = ref<AppLocale>(getLocale())

  // 显示「可以切换到的语言」，而不是当前语言：顶栏按钮的语义是动作目标
  const label = computed(() => (current.value === 'zh-CN' ? 'EN' : '中文'))

  function change(locale: AppLocale) {
    setLocale(locale)
    current.value = locale
  }

  return { current, label, change }
})
