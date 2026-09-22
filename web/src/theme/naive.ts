import type { GlobalThemeOverrides } from 'naive-ui'
import { darkTheme } from 'naive-ui'

/**
 * Naive UI 主题定制。
 *
 * 浅色与暗色两套，取值与 `styles/tokens.css` 对齐——tokens 是 CSS 侧真值源，
 * 这里只做组件层映射，避免同一主色在两处各自定义却逐渐漂移。
 * 主色沿用存量页面的 `--pri: #315ee7`。
 */

const radius = '6px'

export const lightThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#315ee7',
    primaryColorHover: '#2a54d1',
    primaryColorPressed: '#2349b8',
    primaryColorSuppl: '#2a54d1',
    borderRadius: radius,
    fontSize: '14px',
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
  },
  Layout: {
    color: '#f7f8fa',
    siderColor: '#ffffff',
    headerColor: '#ffffff',
  },
  Card: {
    borderRadius: radius,
  },
  DataTable: {
    thColor: '#f7f8fa',
    thFontWeight: '600',
    tdColorHover: '#f2f6ff',
  },
  Menu: {
    itemHeight: '38px',
    borderRadius: radius,
  },
}

export const darkThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#5b83f0',
    primaryColorHover: '#729af5',
    primaryColorPressed: '#4a70d8',
    primaryColorSuppl: '#729af5',
    borderRadius: radius,
    fontSize: '14px',
    bodyColor: '#0f172a',
    cardColor: '#1b2336',
    modalColor: '#1b2336',
    popoverColor: '#1b2336',
    borderColor: '#334155',
    textColorBase: '#f8fafc',
    textColor1: '#f8fafc',
    textColor2: '#cbd5e1',
    textColor3: '#94a3b8',
  },
  Layout: {
    color: '#0f172a',
    siderColor: '#1b2336',
    headerColor: '#1b2336',
  },
  Card: {
    borderRadius: radius,
  },
  DataTable: {
    thColor: '#151d31',
    thFontWeight: '600',
  },
  Menu: {
    itemHeight: '38px',
    borderRadius: radius,
  },
}

export { darkTheme }
