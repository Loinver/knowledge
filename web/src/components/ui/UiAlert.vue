<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import AppIcon from '@/components/AppIcon.vue'

const props = withDefaults(
  defineProps<{
    type?: 'info' | 'success' | 'warning' | 'error' | 'default'
    title?: string
    showIcon?: boolean
    closable?: boolean
  }>(),
  { type: 'info', showIcon: true },
)
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
const color = computed(
  () =>
    `var(--${{ success: 'status-pass', warning: 'status-not-run', error: 'status-violation', info: 'status-info', default: 'foreground-muted' }[props.type]})`,
)
</script>
<template>
  <div
    class="ui-alert"
    :style="{ '--alert-color': color }"
    :role="type === 'error' ? 'alert' : undefined"
  >
    <svg
      v-if="showIcon"
      class="ui-alert-icon"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.5" />
      <path d="M12 7v6m0 4h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
    </svg>
    <div class="ui-alert-body">
      <div v-if="title || $slots.header" class="ui-alert-title">
        <slot name="header">{{ title }}</slot>
      </div>
      <slot />
    </div>
    <button
      v-if="closable"
      type="button"
      class="ui-overlay-close"
      :aria-label="t('common.close')"
      @click="emit('close')"
    >
      <AppIcon name="close" :size="16" />
    </button>
  </div>
</template>
