<script setup lang="ts">
import { useI18n } from 'vue-i18n'
withDefaults(defineProps<{ show?: boolean; description?: string; size?: string }>(), {
  show: false,
})
const { t } = useI18n()
</script>
<template>
  <div class="ui-spinner-wrap" :aria-busy="show">
    <slot />
    <div v-if="show" class="ui-loading-overlay" role="status">
      <span class="ui-spinner" aria-hidden="true" /><span>{{
        description || t('common.loading')
      }}</span>
    </div>
  </div>
</template>
