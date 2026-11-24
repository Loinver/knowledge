<script setup lang="ts">
import { DialogContent, DialogOverlay, DialogPortal } from 'reka-ui'
import { computed, nextTick, provide, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { sheetContextKey } from './overlayTypes'
import { Sheet, SheetTitle } from './primitives/sheet'

defineOptions({ inheritAttrs: false })
const props = withDefaults(
  defineProps<{
    show?: boolean
    width?: number | string
    height?: number | string
    placement?: 'left' | 'right' | 'top' | 'bottom'
    showMask?: boolean
    maskClosable?: boolean
    closeOnEsc?: boolean
    trapFocus?: boolean
    blockScroll?: boolean
  }>(),
  {
    show: false,
    placement: 'right',
    showMask: true,
    maskClosable: true,
    closeOnEsc: true,
    trapFocus: true,
    blockScroll: true,
  },
)
const emit = defineEmits<{ 'update:show': [show: boolean]; 'after-enter': []; 'after-leave': [] }>()
const { t } = useI18n()
const title = ref('')
const id = `sheet-${useId()}`
let origin: HTMLElement | null = null
let transition = 0
const modal = computed(() => props.showMask && props.trapFocus && props.blockScroll)
watch(
  () => props.show,
  async (show, previous) => {
    const current = ++transition
    if (show && typeof document !== 'undefined')
      origin = document.activeElement instanceof HTMLElement ? document.activeElement : null
    if (previous === undefined && !show) return
    await nextTick()
    if (current !== transition || props.show !== show) return
    if (show) emit('after-enter')
    else emit('after-leave')
  },
  { flush: 'sync', immediate: true },
)
const close = () => emit('update:show', false)
provide(sheetContextKey, {
  close,
  setTitle: (value) => (title.value = value),
  locked: computed(() => false),
})
function escape(event: Event) {
  if (!props.closeOnEsc) event.preventDefault()
}
function outside(event: Event) {
  if (!props.maskClosable) event.preventDefault()
}
function focus(event: Event) {
  event.preventDefault()
  if (!props.trapFocus) return
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
  if (!props.show && origin?.isConnected) origin.focus()
}
const dimension = (value?: string | number) => (typeof value === 'number' ? `${value}px` : value)
</script>
<template>
  <Sheet :open="show" :modal="modal" @update:open="!$event && close()">
    <DialogPortal>
      <DialogOverlay v-if="showMask" class="ui-overlay" />
      <DialogContent
        :id="id"
        v-bind="$attrs"
        class="ui-sheet"
        :data-placement="placement"
        :style="{ width: dimension(width), height: dimension(height) }"
        :aria-describedby="undefined"
        @escape-key-down="escape"
        @interact-outside="outside"
        @open-auto-focus="focus"
        @close-auto-focus="returnFocus"
      >
        <SheetTitle class="sr-only">{{ title || t('ds.sheetTitle') }}</SheetTitle>
        <slot />
      </DialogContent>
    </DialogPortal>
  </Sheet>
</template>
