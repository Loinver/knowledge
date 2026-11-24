import { computed, onScopeDispose, ref, shallowRef, watch } from 'vue'

/** An aborted write can still finish on the server. Only its owning session
 * may accept its result, error or loading cleanup. No business state lives here. */
export function useOwnedMutation(owner: () => unknown, formatError: (error: unknown) => string) {
  const busy = ref(false)
  const cause = shallowRef<unknown>(null)
  const error = computed(() => (cause.value === null ? '' : formatError(cause.value)))
  let current: AbortController | undefined
  function invalidate() {
    current?.abort()
    current = undefined
    cause.value = null
    busy.value = false
  }
  watch(owner, invalidate, { flush: 'sync', deep: true })
  onScopeDispose(invalidate)
  async function run<T>(write: (signal: AbortSignal) => Promise<T>): Promise<T | undefined> {
    if (busy.value) return undefined
    const request = new AbortController()
    current = request
    cause.value = null
    busy.value = true
    try {
      const result = await write(request.signal)
      return current === request && !request.signal.aborted ? result : undefined
    } catch (error) {
      if (current === request && !request.signal.aborted) cause.value = error
      return undefined
    } finally {
      if (current === request && !request.signal.aborted) busy.value = false
    }
  }
  return { busy, error, run, invalidate }
}
