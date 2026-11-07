<script setup lang="ts">
import { NAlert, NButton, NCollapse, NCollapseItem, NSelect } from 'naive-ui'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { SemanticViewConfig, SemanticViewFields } from '@/api/graph'

import { fieldsFor, type SemanticBinding, semanticBindings } from './layouts/semanticView'

const props = defineProps<{
  layoutId: string
  config: SemanticViewConfig
  catalog: SemanticViewFields | null
  loading: boolean
  error: string
}>()
const emit = defineEmits<{ change: [config: SemanticViewConfig]; retry: [] }>()
const { t, locale } = useI18n()
const bindings = computed(() => semanticBindings(props.layoutId))
const options = (binding: SemanticBinding) => {
  const fields = fieldsFor(binding, props.catalog?.fields ?? [])
  return [
    ...new Map(
      fields.map((field) => [
        field.iri,
        {
          value: field.iri,
          label: `${field.label_i18n?.[locale.value] || field.name} · ${field.iri}`,
        },
      ]),
    ).values(),
  ]
}
function change(binding: SemanticBinding, iri: string | null) {
  emit('change', { ...props.config, [binding]: iri })
}
</script>

<template>
  <NCollapse v-if="bindings.length" class="semantic-config">
    <NCollapseItem :title="t('semanticView.title')" name="semantic">
      <p>{{ t('semanticView.pin', { revision: catalog?.ontology_revision ?? '—' }) }}</p>
      <NAlert v-if="error" type="warning">
        {{ error }}
        <NButton size="small" @click="emit('retry')">{{ t('graph.refresh') }}</NButton>
      </NAlert>
      <NAlert v-else-if="catalog?.stale" type="warning">{{ t('semanticView.stale') }}</NAlert>
      <div class="semantic-fields">
        <label v-for="binding in bindings" :key="binding">
          <span>{{ t(`semanticView.${binding}`) }}</span>
          <NSelect
            :value="config[binding] ?? null"
            :options="options(binding)"
            :loading="loading"
            :disabled="loading || !catalog || catalog.stale"
            :aria-label="t(`semanticView.${binding}`)"
            :placeholder="t('semanticView.select')"
            filterable
            clearable
            @update:value="change(binding, $event)"
          />
          <small v-if="catalog && !options(binding).length">{{ t('semanticView.noFields') }}</small>
        </label>
      </div>
      <p v-if="bindings.includes('time_property_iri')">{{ t('semanticView.utc') }}</p>
      <p v-if="bindings.includes('latitude_property_iri')">{{ t('semanticView.wgs84') }}</p>
      <p v-if="bindings.includes('measure_property_iri')">
        {{ t('semanticView.positiveMeasure') }}
      </p>
      <p v-if="bindings.includes('hierarchy_relation_iri')">
        {{ t('semanticView.hierarchyDirection') }}
      </p>
    </NCollapseItem>
  </NCollapse>
</template>

<style scoped>
.semantic-config {
  padding: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-medium);
}
.semantic-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr));
  gap: var(--space-3);
}
label {
  display: grid;
  gap: var(--space-2);
  min-width: 0;
}
p,
small {
  color: var(--text-secondary);
}
</style>
