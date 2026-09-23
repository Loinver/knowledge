import type { GlobalThemeOverrides } from 'naive-ui'
import { darkTheme } from 'naive-ui'

/**
 * Naive UI 主题定制。
 *
 * 取值与 `styles/tokens.css` 严格对齐 —— tokens 是 CSS 侧真值源，
 * 这里只做组件层映射，避免同一主色在两处各自定义却逐渐漂移。
 *
 * 深色是主基调（见 `stores/ui.ts` 的默认主题），浅色是同一设计语言的亮色变体：
 * 两者共用同一套语义（品牌双轴、图谱语义色、四态），只换取值。
 */

const radius = '8px'
const radiusLg = '12px'

const fontFamily =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif'

/** 浅色变体：与 tokens.css 的 :root 对齐 */
export const lightThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#2f6fe4',
    primaryColorHover: '#2861cd',
    primaryColorPressed: '#2153b4',
    primaryColorSuppl: '#2861cd',
    infoColor: '#2f6fe4',
    successColor: '#059669',
    warningColor: '#d97706',
    errorColor: '#dc2626',
    borderRadius: radius,
    fontSize: '14px',
    fontFamily,
    bodyColor: '#f7f8fb',
    cardColor: '#ffffff',
    modalColor: '#ffffff',
    popoverColor: '#ffffff',
    borderColor: '#e3e7ee',
    dividerColor: '#e3e7ee',
    hoverColor: '#f0f3f9',
    textColorBase: '#141a24',
    textColor1: '#141a24',
    textColor2: '#5a6478',
    textColor3: '#8a93a6',
    textColorDisabled: '#b4bac7',
    placeholderColor: '#b4bac7',
  },
  Layout: {
    color: '#f7f8fb',
    siderColor: '#ffffff',
    headerColor: '#ffffff',
  },
  Card: {
    borderRadius: radiusLg,
    color: '#ffffff',
    borderColor: 'rgba(20, 26, 36, 0.06)',
  },
  DataTable: {
    borderRadius: radius,
    thColor: '#f2f4f8',
    thTextColor: '#5a6478',
    thFontWeight: '500',
    tdColorHover: '#f0f3f9',
    borderColor: 'rgba(20, 26, 36, 0.06)',
  },
  Menu: {
    itemHeight: '34px',
    borderRadius: radius,
    itemTextColor: '#5a6478',
    itemIconColor: '#8a93a6',
    itemColorActive: 'rgba(47, 111, 228, 0.10)',
    itemColorActiveHover: 'rgba(47, 111, 228, 0.16)',
    itemTextColorActive: '#2153b4',
    itemTextColorActiveHover: '#2153b4',
    itemIconColorActive: '#2f6fe4',
    itemIconColorActiveHover: '#2f6fe4',
  },
  Input: {
    borderRadius: radius,
    color: '#f2f4f8',
    colorFocus: '#f2f4f8',
    border: 'rgba(20, 26, 36, 0.10)',
    borderHover: 'rgba(20, 26, 36, 0.20)',
    borderFocus: '#2f6fe4',
    boxShadowFocus: '0 0 0 3px rgba(47, 111, 228, 0.16)',
  },
  Button: {
    borderRadius: radius,
  },
  Tag: {
    borderRadius: '999px',
  },
}

/** 深色主基调：与 tokens.css 的 [data-theme='dark'] 对齐 */
export const darkThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#4f8df7',
    primaryColorHover: '#6ba0ff',
    primaryColorPressed: '#3d78de',
    primaryColorSuppl: '#6ba0ff',
    infoColor: '#4f8df7',
    successColor: '#34d399',
    warningColor: '#fbbf24',
    errorColor: '#f87171',
    borderRadius: radius,
    fontSize: '14px',
    fontFamily,
    bodyColor: '#080b14',
    cardColor: '#0e1320',
    modalColor: '#141b2d',
    popoverColor: '#141b2d',
    borderColor: 'rgba(255, 255, 255, 0.10)',
    dividerColor: 'rgba(255, 255, 255, 0.06)',
    hoverColor: '#1a2338',
    textColorBase: '#e9eef9',
    textColor1: '#e9eef9',
    textColor2: '#9aa6bf',
    textColor3: '#626e88',
    textColorDisabled: '#414b61',
    placeholderColor: '#414b61',
  },
  Layout: {
    color: '#080b14',
    siderColor: '#0b0f1b',
    headerColor: '#0b0f1b',
  },
  Card: {
    borderRadius: radiusLg,
    color: '#0e1320',
    borderColor: 'rgba(255, 255, 255, 0.06)',
  },
  DataTable: {
    borderRadius: radius,
    thColor: '#0a0f1a',
    thTextColor: '#626e88',
    thFontWeight: '500',
    tdColorHover: '#1a2338',
    borderColor: 'rgba(255, 255, 255, 0.06)',
  },
  Menu: {
    itemHeight: '34px',
    borderRadius: radius,
    itemTextColor: '#9aa6bf',
    itemIconColor: '#626e88',
    itemColorActive: 'rgba(79, 141, 247, 0.14)',
    itemColorActiveHover: 'rgba(79, 141, 247, 0.20)',
    itemTextColorActive: '#bfd4fb',
    itemTextColorActiveHover: '#bfd4fb',
    itemIconColorActive: '#4f8df7',
    itemIconColorActiveHover: '#4f8df7',
  },
  Input: {
    borderRadius: radius,
    color: '#0a0f1a',
    colorFocus: '#0a0f1a',
    border: 'rgba(255, 255, 255, 0.10)',
    borderHover: 'rgba(255, 255, 255, 0.18)',
    borderFocus: '#4f8df7',
    boxShadowFocus: '0 0 0 3px rgba(79, 141, 247, 0.16)',
  },
  Button: {
    borderRadius: radius,
  },
  Tag: {
    borderRadius: '999px',
  },
}

export { darkTheme }
