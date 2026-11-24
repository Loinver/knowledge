<script setup lang="ts">
import { useI18n } from 'vue-i18n'
defineProps<{ description?: string; size?: string }>()
const { t } = useI18n()
</script>
<template>
  <div class="ui-empty" role="status">
    <slot name="icon"
      ><svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="m3 7 4-4h10l4 4v13H3V7Zm0 0h6l1 3h4l1-3h6"
          stroke="currentColor"
          stroke-width="1.25"
          stroke-linejoin="round"
        /></svg
    ></slot>
    <div class="ui-empty-description">
      <slot>{{ description ?? t('ds.empty') }}</slot>
    </div>
    <slot name="extra" />
  </div>
</template>
