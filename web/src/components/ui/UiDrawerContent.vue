<script setup lang="ts">
import type { CSSProperties } from 'vue'
import { inject, onBeforeUnmount, watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'

import AppIcon from '@/components/AppIcon.vue'

import { sheetContextKey } from './overlayTypes'
const props = defineProps<{
  title?: string
  closable?: boolean
  bodyContentStyle?: string | CSSProperties
}>()
const sheet = inject(sheetContextKey, undefined)
const { t } = useI18n()
watchEffect(() => sheet?.setTitle(props.title || ''))
onBeforeUnmount(() => sheet?.setTitle(''))
</script>
<template>
  <div class="ui-sheet-content">
    <header class="ui-overlay-heading">
      <h2 class="ui-overlay-title">
        <slot name="header">{{ title }}</slot>
      </h2>
      <button
        v-if="closable"
        type="button"
        class="ui-overlay-close"
        :aria-label="t('common.close')"
        @click="sheet?.close()"
      >
        <AppIcon name="close" :size="16" />
      </button>
    </header>
    <div class="ui-overlay-body" :style="bodyContentStyle"><slot /></div>
    <footer v-if="$slots.footer" class="ui-overlay-footer"><slot name="footer" /></footer>
  </div>
</template>
