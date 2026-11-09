import { computed, onBeforeUnmount, ref, shallowRef, watch, watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'

import type { KnowledgeDocument, KnowledgeHit, KnowledgePageQuery } from '@/api/knowledge'
import { useApiError } from '@/composables/useApiError'

export function useKnowledgeMessage() {
  const { t, te } = useI18n()
  const { toMessage } = useApiError()
  const reason = (value: string | null | undefined) =>
    value
      ? te(`kb.reason.${value}`)
        ? t(`kb.reason.${value}`)
        : t('kb.unknownReason', { reason: value })
      : ''
  function message(error: unknown) {
    const body = error as { params?: { reason?: string } } | undefined
    return [toMessage(error), reason(body?.params?.reason)].filter(Boolean).join(' · ')
  }
  return { message, reason }
}

/** Each dependency change owns one request chain, including bounded background polling. */
export function useKnowledgeRead<T>(
  load: (signal: AbortSignal) => Promise<T | null>,
  poll?: (data: T) => boolean,
) {
  const { message } = useKnowledgeMessage()
  const data = shallowRef<T | null>(null)
  const error = ref('')
  const loading = ref(false)
  const paused = ref(false)
  const cancelled = ref(false)
  const refresh = ref(0)
  let cancelCurrent = () => {}
  watchEffect((cleanup) => {
    void refresh.value
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    let count = 0
    cleanup(() => {
      controller.abort()
      clearTimeout(timer)
    })
    data.value = null
    error.value = ''
    paused.value = false
    cancelled.value = false
    loading.value = true
    cancelCurrent = () => {
      controller.abort()
      clearTimeout(timer)
      loading.value = false
      cancelled.value = true
    }
    const accept = (result: T | null) => {
      if (controller.signal.aborted) return
      data.value = result
      loading.value = false
      if (result && poll?.(result)) {
        if (++count >= 150) {
          paused.value = true
          return
        }
        timer = setTimeout(() => {
          void load(controller.signal).then(accept).catch(fail)
        }, 2000)
      }
    }
    const fail = (err: unknown) => {
      if (controller.signal.aborted) return
      error.value = message(err)
      loading.value = false
    }
    void load(controller.signal).then(accept).catch(fail)
  })
  return {
    data,
    error,
    loading,
    paused,
    cancelled,
    cancel: () => cancelCurrent(),
    reload: () => refresh.value++,
  }
}

/** Writes may finish on the server after abort; stale completion never changes another context. */
export function useKnowledgeAction(context: () => unknown) {
  const { message } = useKnowledgeMessage()
  const busy = ref(false)
  const error = ref('')
  let controller: AbortController | undefined
  const reset = () => {
    controller?.abort()
    controller = undefined
    busy.value = false
    error.value = ''
  }
  watch(context, reset, { flush: 'sync' })
  onBeforeUnmount(reset)
  async function run<T>(write: (signal: AbortSignal) => Promise<T>): Promise<T | undefined> {
    if (busy.value) return undefined
    const current = new AbortController()
    controller = current
    busy.value = true
    error.value = ''
    try {
      const result = await write(current.signal)
      return current.signal.aborted ? undefined : result
    } catch (err) {
      if (!current.signal.aborted) error.value = message(err)
      return undefined
    } finally {
      if (!current.signal.aborted) busy.value = false
    }
  }
  return { busy, error, run }
}

export const activeTask = (doc: KnowledgeDocument) =>
  !!doc.latest_task && ['QUEUED', 'RUNNING'].includes(doc.latest_task.status)

export function pageQuery(query: Record<string, unknown>): KnowledgePageQuery {
  return {
    page: positivePage(query.page),
    page_size: 20,
    q: typeof query.q === 'string' ? query.q : '',
    status: query.status === 'archived' || query.status === 'all' ? query.status : 'active',
    sort: query.sort === 'name' ? 'name' : '-updated_at',
  }
}

export function positivePage(value: unknown) {
  const number = Number(value)
  return Number.isSafeInteger(number) && number > 0 ? number : 1
}

/** Python parser offsets count Unicode code points, including astral characters as one. */
export function evidenceSegments(text: string, start: number, end: number) {
  const points = Array.from(text)
  const from = Math.max(0, Math.min(start, points.length))
  const to = Math.max(from, Math.min(end, points.length))
  return [
    points.slice(0, from).join(''),
    points.slice(from, to).join(''),
    points.slice(to).join(''),
  ]
}

export function useHitLocation(hit: () => KnowledgeHit) {
  const { t } = useI18n()
  return computed(() => {
    const location = hit().location
    return [
      hit().section,
      location.row_number != null ? t('kb.row', { n: location.row_number }) : '',
      location.paragraph_number != null ? t('kb.paragraph', { n: location.paragraph_number }) : '',
      t('kb.lines', { start: location.start_line, end: location.end_line }),
    ]
      .filter(Boolean)
      .join(' · ')
  })
}
