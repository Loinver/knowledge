import { computed, ref, shallowRef, watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'

/** Cancel obsolete reads on navigation; never let an old response replace the active result set. */
export function useAsyncData<T>(load: (signal: AbortSignal) => Promise<T | null>) {
  const { t } = useI18n()
  const data = shallowRef<T | null>(null)
  const errorCode = ref<string | null>(null)
  const error = computed(() =>
    errorCode.value === null
      ? ''
      : errorCode.value === 'KG.RESOURCE_NOT_FOUND'
        ? t('graph.notFound')
        : t('graph.requestFailed', { code: errorCode.value }),
  )
  const loading = ref(false)
  const refresh = ref(0)

  watchEffect((onCleanup) => {
    void refresh.value
    const controller = new AbortController()
    onCleanup(() => controller.abort())
    data.value = null
    errorCode.value = null
    loading.value = true
    void load(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) data.value = result
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        errorCode.value = typeof err === 'object' && err && 'code' in err ? String(err.code) : ''
      })
      .finally(() => {
        if (!controller.signal.aborted) loading.value = false
      })
  })

  return { data, error, loading, reload: () => refresh.value++ }
}
