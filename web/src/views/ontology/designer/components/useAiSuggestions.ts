import { onScopeDispose, ref, watch } from 'vue'

import type { aiApi, AiSuggestion, SuggestionKind } from '@/api/ai'

type Context = {
  kind: SuggestionKind
  targetId: number
  datasourceId?: number
  reviewOnly?: boolean
}

export function useAiSuggestions(
  context: () => Context,
  api: typeof aiApi,
  t: (key: string) => string,
  toMessage: (cause: unknown) => string,
  onApplied: (id: number) => void,
) {
  const items = ref<AiSuggestion[]>([])
  const loading = ref(false)
  const busyId = ref<number | null>(null)
  const error = ref('')
  const notice = ref('')
  const loaded = ref(false)
  let generation = 0
  let alive = true

  function reset() {
    generation++
    items.value = []
    loading.value = false
    busyId.value = null
    error.value = ''
    notice.value = ''
    loaded.value = false
  }

  watch(
    () => {
      const { kind, targetId, datasourceId, reviewOnly } = context()
      return [kind, targetId, datasourceId, reviewOnly]
    },
    reset,
    { flush: 'sync' },
  )

  function dispose() {
    alive = false
    reset()
  }
  onScopeDispose(dispose)

  const isCurrent = (request: number) => alive && request === generation

  async function generate(text?: string) {
    if (!alive || busyId.value !== null) return
    const { kind, targetId, datasourceId } = context()
    reset()
    const request = generation
    loading.value = true
    try {
      let result: AiSuggestion[]
      if (kind === 'ONTOLOGY_COMPLETION') {
        result = await api.suggestCompletion(targetId)
      } else if (kind === 'MAPPING_SUGGEST') {
        if (!datasourceId) {
          error.value = t('ai.datasourceRequired')
          return
        }
        result = await api.suggestMapping(targetId, datasourceId)
      } else {
        result = await api.extractDocument(targetId, text ?? '')
      }
      if (!isCurrent(request)) return
      items.value = result
      loaded.value = true
    } catch (cause) {
      if (isCurrent(request)) error.value = toMessage(cause)
    } finally {
      if (isCurrent(request)) loading.value = false
    }
  }

  async function resolve(id: number, action: 'apply' | 'discard') {
    if (
      !alive ||
      context().reviewOnly ||
      loading.value ||
      busyId.value !== null ||
      !items.value.some((item) => item.id === id)
    ) {
      return
    }
    const request = ++generation
    busyId.value = id
    error.value = ''
    notice.value = ''
    try {
      await api[action](id)
      // Expiry only revokes UI ownership; an in-flight apply may still commit on the server.
      if (!isCurrent(request)) return
      items.value = items.value.filter((item) => item.id !== id)
      if (action === 'apply') {
        notice.value = t('ai.applied')
        onApplied(id)
      }
    } catch (cause) {
      if (isCurrent(request)) error.value = toMessage(cause)
    } finally {
      if (isCurrent(request)) busyId.value = null
    }
  }

  return {
    items,
    loading,
    busyId,
    error,
    notice,
    loaded,
    generate,
    apply: (id: number) => resolve(id, 'apply'),
    discard: (id: number) => resolve(id, 'discard'),
    dispose,
  }
}

/** JSON payloads include nested labels and model provenance; never coerce objects to strings. */
export function suggestionPayloadLines(item: AiSuggestion): string[] {
  return Object.entries(item.payload)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => {
      const content = Array.isArray(value)
        ? value
            .map((entry) => (typeof entry === 'object' ? JSON.stringify(entry) : String(entry)))
            .join(', ')
        : typeof value === 'object'
          ? JSON.stringify(value)
          : String(value)
      return `${key}: ${content}`
    })
}
