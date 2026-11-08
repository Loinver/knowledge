import type { GlobalThemeOverrides } from 'naive-ui'
import { darkTheme } from 'naive-ui'

/**
 * Naive UI 主题定制。
 *
 * 取值与 `styles/tokens.css` 严格对齐 —— tokens 是 CSS 侧真值源，
 * 这里只做组件层映射，避免同一主色在两处各自定义却逐渐漂移。
 *
 * 首次使用默认浅色，已有用户主题偏好保留：
 * 两者共用同一套语义（品牌双轴、图谱语义色、四态），只换取值。
 */

const radius = '7px'
const radiusLg = '8px'

const fontFamily =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif'

/** 浅色变体：与 tokens.css 的 :root 对齐 */
export const lightThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#235dcc',
    primaryColorHover: '#194fae',
    primaryColorPressed: '#174590',
    primaryColorSuppl: '#194fae',
    infoColor: '#235dcc',
    successColor: '#16734b',
    warningColor: '#975c00',
    errorColor: '#bb2639',
    borderRadius: radius,
    fontSize: '14px',
    fontFamily,
    bodyColor: '#f4f6f8',
    cardColor: '#ffffff',
    modalColor: '#ffffff',
    popoverColor: '#ffffff',
    borderColor: '#dce3eb',
    dividerColor: '#dce3eb',
    hoverColor: '#f0f3f9',
    textColorBase: '#1d2939',
    textColor1: '#1d2939',
    textColor2: '#526174',
    textColor3: '#65758b',
    textColorDisabled: '#b4bac7',
    placeholderColor: '#b4bac7',
  },
  Layout: {
    color: '#f4f6f8',
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
    thColor: '#f4f6f8',
    thTextColor: '#526174',
    thFontWeight: '500',
    tdColorHover: '#f0f3f9',
    borderColor: 'rgba(20, 26, 36, 0.06)',
  },
  Menu: {
    itemHeight: '34px',
    borderRadius: radius,
    itemTextColor: '#526174',
    itemIconColor: '#65758b',
    itemColorActive: 'rgba(47, 111, 228, 0.10)',
    itemColorActiveHover: 'rgba(47, 111, 228, 0.16)',
    itemTextColorActive: '#174590',
    itemTextColorActiveHover: '#174590',
    itemIconColorActive: '#235dcc',
    itemIconColorActiveHover: '#235dcc',
  },
  Input: {
    borderRadius: radius,
    color: '#f4f6f8',
    colorFocus: '#f4f6f8',
    border: '1px solid #dce3eb',
    borderHover: '1px solid #a6b4ca',
    borderFocus: '1px solid #235dcc',
    boxShadowFocus: '0 0 0 3px rgba(47, 111, 228, 0.16)',
  },
  Button: {
    borderRadius: radius,
  },
  Tag: {
    borderRadius: '4px',
  },
}

/** 深色主题：与 tokens.css 的 [data-theme='dark'] 对齐 */
export const darkThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#8bb5ff',
    primaryColorHover: '#aecaff',
    primaryColorPressed: '#709fe8',
    primaryColorSuppl: '#aecaff',
    infoColor: '#8bb5ff',
    successColor: '#34d399',
    warningColor: '#fbbf24',
    errorColor: '#f87171',
    borderRadius: radius,
    fontSize: '14px',
    fontFamily,
    bodyColor: '#111927',
    cardColor: '#192333',
    modalColor: '#202d40',
    popoverColor: '#202d40',
    borderColor: 'rgba(255, 255, 255, 0.10)',
    dividerColor: 'rgba(255, 255, 255, 0.06)',
    hoverColor: '#1a2338',
    textColorBase: '#e4ecf8',
    textColor1: '#e4ecf8',
    textColor2: '#a4b4cc',
    textColor3: '#a4b4cc',
    textColorDisabled: '#7a89a0',
    placeholderColor: '#7a89a0',
  },
  Layout: {
    color: '#111927',
    siderColor: '#152031',
    headerColor: '#152031',
  },
  Card: {
    borderRadius: radiusLg,
    color: '#192333',
    borderColor: 'rgba(255, 255, 255, 0.06)',
  },
  DataTable: {
    borderRadius: radius,
    thColor: '#121d2d',
    thTextColor: '#a4b4cc',
    thFontWeight: '500',
    tdColorHover: '#1a2338',
    borderColor: 'rgba(255, 255, 255, 0.06)',
  },
  Menu: {
    itemHeight: '34px',
    borderRadius: radius,
    itemTextColor: '#a4b4cc',
    itemIconColor: '#a4b4cc',
    itemColorActive: 'rgba(79, 141, 247, 0.14)',
    itemColorActiveHover: 'rgba(79, 141, 247, 0.20)',
    itemTextColorActive: '#bfd4fb',
    itemTextColorActiveHover: '#bfd4fb',
    itemIconColorActive: '#8bb5ff',
    itemIconColorActiveHover: '#8bb5ff',
  },
  Input: {
    borderRadius: radius,
    color: '#121d2d',
    colorFocus: '#121d2d',
    border: '1px solid rgba(255, 255, 255, 0.16)',
    borderHover: '1px solid rgba(255, 255, 255, 0.28)',
    borderFocus: '1px solid #8bb5ff',
    boxShadowFocus: '0 0 0 3px rgba(79, 141, 247, 0.16)',
  },
  Button: {
    borderRadius: radius,
    colorPrimary: '#426eb7',
    colorHoverPrimary: '#4c7ac7',
    colorPressedPrimary: '#365f9f',
    textColorPrimary: '#ffffff',
    textColorHoverPrimary: '#ffffff',
    textColorPressedPrimary: '#ffffff',
  },
  Tag: {
    borderRadius: '4px',
  },
}

export { darkTheme }
