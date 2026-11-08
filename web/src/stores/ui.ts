import { defineStore } from 'pinia'
import { computed, onScopeDispose, ref, watch } from 'vue'

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
 * 首次使用默认浅色；已有 light/dark 偏好保持不变。
 */
export const useUiStore = defineStore('ui', () => {
  const desktopCollapsed = ref(read(SIDER_KEY) === '1')
  const media =
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(max-width: 1199px)')
      : null
  const narrow = ref(media?.matches ?? false)
  const narrowCollapsed = ref(true)
  const collapsed = computed(() => (narrow.value ? narrowCollapsed.value : desktopCollapsed.value))
  function updateViewport(event: MediaQueryListEvent): void {
    narrow.value = event.matches
    if (event.matches) narrowCollapsed.value = true
  }
  media?.addEventListener('change', updateViewport)
  onScopeDispose(() => media?.removeEventListener('change', updateViewport))
  const themeMode = ref<ThemeMode>(read(THEME_KEY) === 'dark' ? 'dark' : 'light')

  const isDark = computed(() => themeMode.value === 'dark')

  function applyTheme(mode: ThemeMode): void {
    if (typeof document === 'undefined') return
    if (mode === 'dark') document.documentElement.dataset.theme = 'dark'
    else delete document.documentElement.dataset.theme
  }

  function toggleSider(): void {
    if (narrow.value) narrowCollapsed.value = !narrowCollapsed.value
    else desktopCollapsed.value = !desktopCollapsed.value
  }

  function toggleTheme(): void {
    themeMode.value = isDark.value ? 'light' : 'dark'
  }

  watch(desktopCollapsed, (value) => {
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
