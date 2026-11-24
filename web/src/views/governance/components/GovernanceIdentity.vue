<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{ name: string; iri?: string; revision?: number; context?: string; nameKey?: string }>()
const { t } = useI18n()
</script>

<template>
  <dl class="governance-identity">
    <div>
      <dt>{{ t(nameKey || 'common.name') }}</dt>
      <dd>{{ name }}</dd>
    </div>
    <div v-if="iri" class="identity-iri">
      <dt>{{ t('common.iri') }}</dt>
      <dd>{{ iri }}</dd>
    </div>
    <div v-if="revision !== undefined">
      <dt>{{ t('common.revision') }}</dt>
      <dd>{{ `r${revision}` }}</dd>
    </div>
    <div v-if="context" class="context">
      <dt>{{ t('common.status') }}</dt>
      <dd>{{ context }}</dd>
    </div>
  </dl>
</template>

<style scoped>
.governance-identity {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
  margin: 0;
  min-width: 0;
}
.governance-identity > div {
  min-width: 0;
}
dt {
  color: var(--text-secondary);
  font-size: 11px;
  margin-bottom: 4px;
}
dd {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 12px;
  overflow-wrap: anywhere;
  color: var(--text-primary);
}
.identity-iri {
  flex: 1 1 240px;
}
.context {
  flex-basis: 100%;
}
.context dd {
  font-family: inherit;
}
</style>
