import { onBeforeUnmount, ref } from 'vue'

import type { FrozenResource, RevisionContents } from '@/api/ontology-history'
import { ontologyHistoryApi } from '@/api/ontology-history'

/** A failed frozen read stays unavailable; current resources are never substituted. */
export function useDesignerHistory(toMessage: (error: unknown) => string) {
  const revision = ref<number | null>(null)
  const contents = ref<RevisionContents | null>(null)
  const resources = ref<Record<number, FrozenResource>>({})
  const loading = ref(false)
  const error = ref('')
  let request: AbortController | undefined

  function reset() {
    request?.abort()
    revision.value = null
    contents.value = null
    resources.value = {}
    loading.value = false
    error.value = ''
  }

  async function load(ontologyId: number, version: number) {
    reset()
    revision.value = version
    const controller = new AbortController()
    request = controller
    loading.value = true
    try {
      const result = await ontologyHistoryApi.contents(ontologyId, version, controller.signal)
      if (controller.signal.aborted) return false
      const snapshots: Record<number, FrozenResource> = {}
      // Keep requests bounded for larger ontologies while retaining atomic display.
      for (let offset = 0; offset < result.resources.length; offset += 8) {
        const batch = await Promise.all(
          result.resources
            .slice(offset, offset + 8)
            .map((item) =>
              ontologyHistoryApi.resource(ontologyId, version, item.resource_id, controller.signal),
            ),
        )
        if (controller.signal.aborted) return false
        for (const resource of batch) snapshots[resource.resource_id] = resource
      }
      contents.value = result
      resources.value = snapshots
      return true
    } catch (err) {
      if (!controller.signal.aborted) error.value = toMessage(err)
      return false
    } finally {
      if (!controller.signal.aborted) loading.value = false
    }
  }

  onBeforeUnmount(reset)
  return { revision, contents, resources, loading, error, load, reset }
}
