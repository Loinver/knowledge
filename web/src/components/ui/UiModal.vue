<script setup lang="ts">
import { DialogContent, DialogOverlay, DialogPortal } from 'reka-ui'
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppIcon from '@/components/AppIcon.vue'

import { Dialog, DialogTitle } from './primitives/dialog'
import UiButton from './UiButton.vue'

defineOptions({ inheritAttrs: false })
const props = withDefaults(
  defineProps<{
    show?: boolean
    title?: string
    content?: string
    preset?: string
    closable?: boolean
    maskClosable?: boolean
    closeOnEsc?: boolean
    positiveText?: string
    negativeText?: string
    restoreFocusTo?: HTMLElement | null
    positiveButtonProps?: { loading?: boolean; disabled?: boolean }
    onPositiveClick?: (event: MouseEvent) => unknown | Promise<unknown>
    onNegativeClick?: (event: MouseEvent) => unknown | Promise<unknown>
  }>(),
  { show: false, closable: true, maskClosable: true, closeOnEsc: true },
)
const emit = defineEmits<{
  'update:show': [show: boolean]
  close: []
  'after-enter': []
  'after-leave': []
}>()
const { t } = useI18n()
const id = `dialog-${useId()}`
const busy = ref(false)
const failed = ref(false)
const locked = computed(() => busy.value || props.positiveButtonProps?.loading)
let origin: HTMLElement | null = null
let transition = 0
let actionIdentity = 0
let disposed = false
onBeforeUnmount(() => {
  disposed = true
  transition++
})
watch(
  () => props.show,
  async (show, previous) => {
    const current = ++transition
    actionIdentity++
    busy.value = false
    failed.value = false
    if (show && typeof document !== 'undefined')
      origin = document.activeElement instanceof HTMLElement ? document.activeElement : null
    if (previous === undefined && !show) return
    await nextTick()
    if (disposed || current !== transition || props.show !== show) return
    if (show) emit('after-enter')
    else emit('after-leave')
  },
  { flush: 'sync', immediate: true },
)
function dismiss() {
  if (locked.value) return
  emit('update:show', false)
  emit('close')
}
function escape(event: Event) {
  if (!props.closeOnEsc || locked.value) event.preventDefault()
}
function outside(event: Event) {
  if (!props.maskClosable || locked.value) event.preventDefault()
}
function focus(event: Event) {
  event.preventDefault()
  void nextTick(() => {
    const content = document.getElementById(id)
    const input = content?.querySelector<HTMLElement>(
      'input:not(:disabled),textarea:not(:disabled),[role="combobox"]:not([disabled]),[autofocus]',
    )
    ;(input || content)?.focus()
  })
}
function returnFocus(event: Event) {
  event.preventDefault()
  const target = props.restoreFocusTo || origin
  if (!props.show && target?.isConnected) target.focus()
}
async function action(positive: boolean, event: MouseEvent) {
  if (locked.value) return
  const current = transition
  const actionId = ++actionIdentity
  busy.value = true
  failed.value = false
  try {
    const result = await (positive
      ? props.onPositiveClick?.(event)
      : props.onNegativeClick?.(event))
    if (result !== false && !disposed && current === transition && actionId === actionIdentity)
      emit('update:show', false)
  } catch {
    if (!disposed && current === transition && actionId === actionIdentity) failed.value = true
  } finally {
    if (!disposed && current === transition && actionId === actionIdentity) busy.value = false
  }
}
</script>
<template>
  <Dialog :open="show" @update:open="!$event && dismiss()">
    <DialogPortal>
      <DialogOverlay class="ui-overlay" />
      <DialogContent
        :id="id"
        v-bind="$attrs"
        class="ui-dialog"
        :aria-describedby="undefined"
        @escape-key-down="escape"
        @interact-outside="outside"
        @open-auto-focus="focus"
        @close-auto-focus="returnFocus"
      >
        <header class="ui-overlay-heading">
          <DialogTitle class="ui-overlay-title">{{ title || t('ds.dialogTitle') }}</DialogTitle>
          <button
            v-if="closable"
            type="button"
            class="ui-overlay-close"
            :disabled="locked"
            :aria-label="t('common.close')"
            @click="dismiss"
          >
            <AppIcon name="close" :size="16" />
          </button>
        </header>
        <div class="ui-overlay-body">
          <slot>{{ content }}</slot>
          <p v-if="failed" class="ui-field-error" role="alert">{{ t('ds.actionFailed') }}</p>
        </div>
        <footer
          v-if="$slots.action || $slots.footer || positiveText || negativeText"
          class="ui-overlay-footer"
        >
          <slot name="action"
            ><slot name="footer">
              <div class="ui-form-actions">
                <UiButton v-if="negativeText" :disabled="locked" @click="action(false, $event)">{{
                  negativeText
                }}</UiButton>
                <UiButton
                  v-if="positiveText"
                  type="primary"
                  :loading="locked"
                  :disabled="positiveButtonProps?.disabled"
                  @click="action(true, $event)"
                  >{{ positiveText }}</UiButton
                >
              </div>
            </slot></slot
          >
        </footer>
      </DialogContent>
    </DialogPortal>
  </Dialog>
</template>
