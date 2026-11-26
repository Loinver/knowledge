<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { DomainBrief } from '@/api/domains'
import { UiButton } from '@/components/ui'

defineProps<{ domains: DomainBrief[]; value: number | null; loading?: boolean; error?: string }>()
defineEmits<{ 'update:value': [value: number | null]; retry: [] }>()
const { t, locale } = useI18n()
</script>

<template>
  <aside class="domain-sidebar" :aria-label="t('page.domains')" :aria-busy="loading">
    <h2>{{ t('page.domains') }}</h2>
    <button type="button" :aria-pressed="value === null" @click="$emit('update:value', null)">
      {{ t('entityType.allDomains') }}
    </button>
    <p v-if="error" role="alert">
      {{ error }} <UiButton size="small" @click="$emit('retry')">{{ t('ui.retry') }}</UiButton>
    </p>
    <p v-else-if="loading" role="status">{{ t('common.loading') }}</p>
    <template v-else>
      <button
        v-for="domain in domains"
        :key="domain.id"
        type="button"
        :aria-pressed="value === domain.id"
        @click="$emit('update:value', domain.id)"
      >
        <span class="domain-mark" aria-hidden="true" />
        <span>{{ domain.label_i18n?.[locale]?.trim() || t('enumDictionaries.untranslated') }}</span>
      </button>
      <p v-if="!domains.length">{{ t('common.empty') }}</p>
    </template>
  </aside>
</template>

<style scoped>
.domain-sidebar {
  min-width: 0;
  padding: 16px 10px;
  background: var(--surface-muted);
  border: 1px solid var(--border-muted);
  border-radius: var(--radius-panel);
}
h2 {
  margin: 0 8px 16px;
  font-size: 13px;
}
button {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 38px;
  padding: 9px 10px;
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--foreground-muted);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  text-align: left;
  overflow-wrap: anywhere;
}
button[aria-pressed='true'] {
  background: var(--surface-selected);
  color: var(--action-primary);
  font-weight: 600;
}
button:hover {
  background: var(--surface-hover);
}
button:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}
.domain-mark {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  border: 1px solid currentColor;
  transform: rotate(45deg);
}
p {
  margin: 12px 8px;
  font-size: 12px;
  color: var(--foreground-muted);
  overflow-wrap: anywhere;
}
</style>
