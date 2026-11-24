<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { ResourceStatus } from '@/api/entity-types'

defineProps<{
  name: string
  iri?: string
  revision?: number
  status?: ResourceStatus
  context?: string
}>()
const { t } = useI18n()
</script>

<template>
  <dl class="asset-identity">
    <div>
      <dt>{{ t('common.name') }}</dt>
      <dd class="mono">{{ name }}</dd>
    </div>
    <div v-if="iri" class="identity-iri">
      <dt>{{ t('common.iri') }}</dt>
      <dd class="mono">{{ iri }}</dd>
    </div>
    <div v-if="revision !== undefined">
      <dt>{{ t('common.revision') }}</dt>
      <dd class="mono">{{ `r${revision}` }}</dd>
    </div>
    <div v-if="status">
      <dt>{{ t('common.status') }}</dt>
      <dd class="identity-state" :data-state="status">
        <i aria-hidden="true" />
        <span class="mono">{{ status }}</span> · {{ t(`resourceStatus.${status}`) }}
      </dd>
    </div>
    <div v-if="context" class="identity-context">
      <dt>{{ t('common.status') }}</dt>
      <dd>{{ context }}</dd>
    </div>
  </dl>
</template>

<style scoped>
.asset-identity {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
  margin: 0;
  min-width: 0;
}
.asset-identity > div {
  min-width: 0;
}
.identity-iri {
  flex: 1 1 260px;
}
dt {
  color: var(--text-secondary);
  font-size: 11px;
  margin-bottom: 4px;
}
dd {
  margin: 0;
  color: var(--text-primary);
  overflow-wrap: anywhere;
  font-size: 12px;
}
.mono {
  font-family: var(--font-mono);
}
.identity-state {
  display: flex;
  align-items: center;
  gap: 6px;
}
.identity-state i {
  width: 6px;
  height: 6px;
  background: var(--s-na);
  border-radius: 50%;
}
.identity-state[data-state='PUBLISHED'] i {
  background: var(--s-pass);
}
.identity-state[data-state='DRAFT'] i {
  background: var(--s-notrun);
}
.identity-context {
  flex-basis: 100%;
}
@media (max-width: 640px) {
  .identity-iri {
    flex-basis: 100%;
  }
}
</style>
