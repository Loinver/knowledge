<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="page-placeholder">{{ t('page.mappingWizard') }}</div>
</template>

<style scoped>
.page-placeholder {
  padding: 24px;
  font-size: 18px;
  font-weight: 600;
  color: var(--text);
}
</style>
