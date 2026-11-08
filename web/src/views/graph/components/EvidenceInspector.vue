<script setup lang="ts">
import { NTag } from 'naive-ui'
import { useI18n } from 'vue-i18n'

import type { EvidenceItem } from '@/api/graph'

defineProps<{ items: EvidenceItem[] }>()
const { t } = useI18n()
</script>

<template>
  <article v-for="item in items" :key="item.id" class="evidence-card">
    <header>
      <strong>{{ item.source_name ?? t('graph.deletedSource') }}</strong>
      <NTag size="small" :type="item.quarantined ? 'warning' : 'default'">{{
        item.quarantined ? t('graph.hasQuarantine') : t(`graph.evidenceTypes.${item.evidence_type}`)
      }}</NTag>
    </header>
    <dl>
      <dt>{{ t('graph.source') }}</dt>
      <dd>{{ item.source_id }} · {{ item.source_kind ?? '—' }}</dd>
      <dt>{{ t('graph.table') }}</dt>
      <dd>{{ item.table_name }}</dd>
      <dt>{{ t('graph.rowKey') }}</dt>
      <dd>{{ item.row_key }}</dd>
      <dt>{{ t('graph.fields') }}</dt>
      <dd>{{ item.columns.join(', ') || '—' }}</dd>
      <dt>{{ t('graph.chainRun') }}</dt>
      <dd>{{ item.run_id }}</dd>
      <dt>{{ t('graph.chainMapping') }}</dt>
      <dd>{{ item.mapping_revision_id ?? t('graph.chainUnpinned') }}</dd>
      <dt>{{ t('graph.chainOntology') }}</dt>
      <dd>{{ item.ontology_revision ?? t('graph.chainUnpinned') }}</dd>
    </dl>
    <details v-if="item.column_transforms?.length">
      <summary>{{ t('graph.chainTransforms') }}</summary>
      <pre>{{ JSON.stringify(item.column_transforms, null, 2) }}</pre>
    </details>
    <details v-if="item.resource_revisions || item.rule_revisions">
      <summary>{{ t('graph.chainResources') }}</summary>
      <pre>{{
        JSON.stringify({ resources: item.resource_revisions, rules: item.rule_revisions }, null, 2)
      }}</pre>
    </details>
  </article>
</template>

<style scoped>
.evidence-card {
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-medium);
  background: var(--bg-surface);
}
header {
  display: flex;
  gap: 8px;
  justify-content: space-between;
  align-items: start;
}
dl {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: 8px;
  margin-bottom: 0;
  font-size: 12px;
}
dt {
  color: var(--text-secondary);
}
dd {
  margin: 0;
  overflow-wrap: anywhere;
}
details {
  margin-top: 12px;
  font-size: 12px;
}
summary {
  cursor: pointer;
  color: var(--pri);
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
