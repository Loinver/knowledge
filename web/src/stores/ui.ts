import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

const SIDER_KEY = 'kg-sider-collapsed'
const THEME_KEY = 'kg-theme-mode'

export type ThemeMode = 'light' | 'dark'

function read(key: string): string | null {
  return typeof localStorage === 'undefined' ? null : localStorage.getItem(key)
}

/**
 * 界面偏好：侧栏折叠与浅暗主题。
 *
 * 两项都持久化到 localStorage，并在 store 创建时立刻应用到 `<html>`，
 * 避免刷新后先渲染浅色再跳暗色的闪烁。
 *
 * 默认主题是**深色**——设计语言「星图」以深空为基调，浅色是它的亮色变体。
 * 只有用户显式切到浅色（localStorage 里存了 `light`）才会离开深色。
 */
export const useUiStore = defineStore('ui', () => {
  const collapsed = ref(read(SIDER_KEY) === '1')
  const themeMode = ref<ThemeMode>(read(THEME_KEY) === 'light' ? 'light' : 'dark')

  const isDark = computed(() => themeMode.value === 'dark')

  function applyTheme(mode: ThemeMode): void {
    if (typeof document === 'undefined') return
    if (mode === 'dark') document.documentElement.dataset.theme = 'dark'
    else delete document.documentElement.dataset.theme
  }

  function toggleSider(): void {
    collapsed.value = !collapsed.value
  }

  function toggleTheme(): void {
    themeMode.value = isDark.value ? 'light' : 'dark'
  }

  watch(collapsed, (value) => {
    if (typeof localStorage !== 'undefined') localStorage.setItem(SIDER_KEY, value ? '1' : '0')
  })

  watch(
    themeMode,
    (value) => {
      applyTheme(value)
      if (typeof localStorage !== 'undefined') localStorage.setItem(THEME_KEY, value)
    },
    { immediate: true },
  )

  return { collapsed, themeMode, isDark, toggleSider, toggleTheme, applyTheme }
})
