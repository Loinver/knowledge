<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import UiButton from './UiButton.vue'
import UiPopover from './UiPopover.vue'

const props = defineProps<{
  positiveText?: string
  negativeText?: string
  disabled?: boolean
  showIcon?: boolean
  onPositiveClick?: (event: MouseEvent) => unknown | Promise<unknown>
  onNegativeClick?: (event: MouseEvent) => unknown | Promise<unknown>
}>()
const { t } = useI18n()
const show = ref(false)
const busy = ref(false)
const failed = ref(false)
let session = 0
let actionIdentity = 0
let disposed = false
watch(
  show,
  () => {
    session++
    actionIdentity++
    busy.value = false
    failed.value = false
  },
  { flush: 'sync' },
)
onBeforeUnmount(() => {
  disposed = true
  session++
  actionIdentity++
})
async function action(positive: boolean, event: MouseEvent) {
  if (busy.value || props.disabled || !show.value) return
  const currentSession = session
  const currentAction = ++actionIdentity
  busy.value = true
  failed.value = false
  try {
    const result = await (positive
      ? props.onPositiveClick?.(event)
      : props.onNegativeClick?.(event))
    if (
      !disposed &&
      currentSession === session &&
      currentAction === actionIdentity &&
      result !== false
    )
      show.value = false
  } catch {
    if (!disposed && currentSession === session && currentAction === actionIdentity)
      failed.value = true
  } finally {
    if (!disposed && currentSession === session && currentAction === actionIdentity)
      busy.value = false
  }
}
const confirm = (event: MouseEvent) => action(true, event)
const cancel = (event: MouseEvent) => action(false, event)
</script>
<template>
  <UiPopover v-model:show="show" :disabled="disabled" trigger="click">
    <template #trigger><slot name="trigger" /></template>
    <div role="alertdialog" :aria-label="t('common.confirm')" class="ui-confirm">
      <div class="ui-confirm-content"><slot /></div>
      <p v-if="failed" class="ui-field-error" role="alert">{{ t('ds.actionFailed') }}</p>
      <div class="ui-form-actions">
        <UiButton :disabled="busy" @click="cancel">{{
          negativeText || t('common.cancel')
        }}</UiButton
        ><UiButton type="primary" :loading="busy" @click="confirm">{{
          positiveText || t('common.confirm')
        }}</UiButton>
      </div>
    </div>
  </UiPopover>
</template>
<style scoped>
.ui-confirm {
  max-width: 320px;
  padding: var(--space-3);
}
.ui-confirm-content {
  margin-bottom: var(--space-4);
}
</style>
