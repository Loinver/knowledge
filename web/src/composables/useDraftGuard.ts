import type { Ref } from 'vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteLeave } from 'vue-router'

/** Keep the raw open ref for successful saves; bind this model to user close actions. */
export function useDraftGuard(
  open: Ref<boolean>,
  value: () => unknown,
  ready: () => boolean = () => true,
) {
  const { t } = useI18n()
  const baseline = ref<string>()
  const serialize = () => JSON.stringify(value())
  watch(
    [open, ready],
    ([visible, isReady]) => {
      baseline.value = visible && isReady ? serialize() : undefined
    },
    { immediate: true, flush: 'post' },
  )
  const dirty = computed(
    () => open.value && ready() && baseline.value !== undefined && baseline.value !== serialize(),
  )
  const confirm = () =>
    !dirty.value || (typeof window !== 'undefined' && window.confirm(t('ui.unsaved')))
  const visible = computed({
    get: () => open.value,
    set: (next: boolean) => {
      if (next || confirm()) open.value = next
    },
  })
  onBeforeRouteLeave(() => confirm())
  const beforeUnload = (event: BeforeUnloadEvent) => {
    if (!dirty.value) return
    event.preventDefault()
    event.returnValue = ''
  }
  onMounted(() => {
    if (typeof window !== 'undefined') window.addEventListener('beforeunload', beforeUnload)
  })
  onBeforeUnmount(() => {
    if (typeof window !== 'undefined') window.removeEventListener('beforeunload', beforeUnload)
  })
  return visible
}
