<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { SemanticViewConfig, SemanticViewFields } from '@/api/graph'
import { UiAlert, UiButton, UiCollapse, UiCollapseItem, UiSelect } from '@/components/ui'

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
          label: `${field.label_i18n?.[locale.value]?.trim() || `${field.name} · ${t('enumDictionaries.untranslated')}`} · ${field.iri}`,
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
  <UiCollapse v-if="bindings.length" class="semantic-config">
    <UiCollapseItem :title="t('semanticView.title')" name="semantic">
      <p>{{ t('semanticView.pin', { revision: catalog?.ontology_revision ?? '—' }) }}</p>
      <UiAlert v-if="error" type="warning">
        {{ error }}
        <UiButton size="small" @click="emit('retry')">{{ t('graph.refresh') }}</UiButton>
      </UiAlert>
      <UiAlert v-else-if="catalog?.stale" type="warning">{{ t('semanticView.stale') }}</UiAlert>
      <div class="semantic-fields">
        <label v-for="binding in bindings" :key="binding">
          <span>{{ t(`semanticView.${binding}`) }}</span>
          <UiSelect
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
    </UiCollapseItem>
  </UiCollapse>
</template>

<style scoped>
.semantic-config {
  padding: var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-control);
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
  color: var(--foreground-secondary);
}
</style>
