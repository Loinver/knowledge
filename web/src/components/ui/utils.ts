import { useI18n } from 'vue-i18n'

export { cn } from 'cn'

type PrimitiveMessageKey = 'close' | 'first' | 'last' | 'next' | 'previous' | 'more'

// The project language packs are the sole source of primitive default messages.
export function usePrimitiveI18n() {
  const { t } = useI18n({ useScope: 'global' })
  return { t: (key: PrimitiveMessageKey) => t(`ds.primitives.${key}`) }
}
