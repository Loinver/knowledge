<script setup lang="ts">
import { ToastClose, ToastDescription, ToastProvider, ToastRoot, ToastViewport } from 'reka-ui'
import { provide, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import AppIcon from '@/components/AppIcon.vue'

import type { DialogOptions, FeedbackKind, FeedbackText, MessageApi } from './feedback'
import { dialogKey, messageKey } from './feedback'
import UiModal from './UiModal.vue'

type Notice = {
  id: number
  kind: FeedbackKind
  text: FeedbackText
  duration: number
  open: boolean
}
const { t } = useI18n()
let serial = 0
const notices = ref<Notice[]>([])
const dialog = ref<{ id: number; options: DialogOptions } | null>(null)
const resolve = (value?: FeedbackText) => (typeof value === 'function' ? value() : value)
const closeFor = (id: number) => (show: boolean) => {
  if (!show && dialog.value?.id === id) dialog.value = null
}
function add(kind: FeedbackKind, text: FeedbackText, options?: { duration?: number }) {
  const id = ++serial
  notices.value = [
    ...notices.value.slice(-4),
    {
      id,
      kind,
      text,
      duration: options?.duration === 0 ? Infinity : (options?.duration ?? 5000),
      open: true,
    },
  ]
  return {
    destroy: () => {
      notices.value = notices.value.filter((item) => item.id !== id)
    },
  }
}
const api: MessageApi = {
  success: (text, options) => add('success', text, options),
  error: (text, options) => add('error', text, options),
  warning: (text, options) => add('warning', text, options),
  info: (text, options) => add('info', text, options),
}
provide(messageKey, api)
provide(dialogKey, {
  warning: (options) => {
    const id = ++serial
    dialog.value = { id, options }
    return {
      destroy: () => {
        if (dialog.value?.id === id) dialog.value = null
      },
    }
  },
})
</script>
<template>
  <ToastProvider :duration="5000" :label="t('ds.notifications')" swipe-direction="right">
    <slot />
    <ToastRoot
      v-for="notice in notices"
      :key="notice.id"
      :open="notice.open"
      :duration="notice.duration"
      class="ui-toast"
      :data-kind="notice.kind"
      @update:open="!$event && (notices = notices.filter((item) => item.id !== notice.id))"
    >
      <ToastDescription class="ui-toast-body">{{ resolve(notice.text) }}</ToastDescription>
      <ToastClose class="ui-overlay-close" :aria-label="t('common.close')"
        ><AppIcon name="close" :size="16"
      /></ToastClose>
    </ToastRoot>
    <ToastViewport class="ui-toast-viewport" :label="t('ds.notifications')" />
  </ToastProvider>
  <UiModal
    v-if="dialog"
    :key="dialog.id"
    :show="true"
    :title="resolve(dialog.options.title)"
    :content="resolve(dialog.options.content)"
    :positive-text="resolve(dialog.options.positiveText) || t('common.confirm')"
    :negative-text="resolve(dialog.options.negativeText) || t('common.cancel')"
    :on-positive-click="dialog.options.onPositiveClick"
    :restore-focus-to="dialog.options.restoreFocusTo"
    :on-negative-click="dialog.options.onNegativeClick"
    v-bind="{ 'onUpdate:show': closeFor(dialog.id) }"
  />
</template>
<style scoped>
.ui-toast-viewport {
  position: fixed;
  z-index: var(--z-toast);
  right: var(--space-4);
  bottom: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: min(380px, calc(100vw - 32px));
  max-height: 100dvh;
  padding: 0;
  margin: 0;
  list-style: none;
  outline: none;
}
.ui-toast {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  color: var(--foreground-primary);
  background: var(--surface-overlay);
  border: 1px solid var(--border-default);
  border-left: 3px solid var(--status-info);
  border-radius: var(--radius-control);
  box-shadow: var(--shadow-raised);
}
.ui-toast[data-kind='error'] {
  border-left-color: var(--status-violation);
}
.ui-toast[data-kind='success'] {
  border-left-color: var(--status-pass);
}
.ui-toast[data-kind='warning'] {
  border-left-color: var(--status-not-run);
}
.ui-toast-body {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
