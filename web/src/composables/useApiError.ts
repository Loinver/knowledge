import { useI18n } from 'vue-i18n'

/**
 * 把后端错误码翻译成界面文案。
 *
 * 项目硬规则：界面永远用 `code` 走 i18n，绝不把 `code` 或英文 `message`
 * 直接展示给用户。未见过的码要显示「未知错误 + code」，不能吞掉。
 */
export function useApiError() {
  const { t, te } = useI18n()

  function toMessage(err: unknown): string {
    const body = err as { code?: unknown; params?: Record<string, unknown> } | undefined
    const code = typeof body?.code === 'string' ? body.code : ''
    if (!code) return t('errors.network')
    const key = `errors.${code}`
    if (te(key)) return t(key, body?.params ?? {})
    return t('errors.unknown', { code })
  }

  return { toMessage }
}
