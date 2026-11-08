<script setup lang="ts">
import { NAlert, NEmpty } from 'naive-ui'
import { useI18n } from 'vue-i18n'

import type { MappingRevision } from '@/api/mappings'

defineProps<{ revision: MappingRevision }>()
const { t } = useI18n()
function fields(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value : []
}
function display(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  return typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)
}
</script>

<template>
  <div class="frozen-mapping">
    <NAlert type="info">{{ t('extractionUi.frozenDetail') }}</NAlert>
    <section v-for="(map, index) in revision.entity_maps" :key="index" class="mapping-section">
      <h3>{{ map.entity_type }}</h3>
      <p class="mono">{{ `${map.schema}.${map.table}` }}</p>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{{ t('dataAccess.mapping.targetAttribute') }}</th>
              <th>{{ t('dataAccess.mapping.sourceField') }}</th>
              <th>{{ t('dataAccess.mapping.transform') }}</th>
              <th>{{ t('dataAccess.mapping.nullPolicy') }}</th>
              <th>{{ t('dataAccess.mapping.defaultValue') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(field, fieldIndex) in fields(map.field_maps)" :key="fieldIndex">
              <td>{{ field.target_attr }}</td>
              <td class="mono">{{ field.source_field }}</td>
              <td>
                {{ t(`dataAccess.mapping.transforms.${field.transform}`, String(field.transform)) }}
                <pre v-if="field.transform_params">{{ display(field.transform_params) }}</pre>
              </td>
              <td>
                {{
                  t(
                    `dataAccess.mapping.nullPolicies.${field.null_policy}`,
                    String(field.null_policy),
                  )
                }}
              </td>
              <td>{{ display(field.default_value) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <dl>
        <dt>{{ t('dataAccess.mapping.keyFields') }}</dt>
        <dd>{{ display(map.key_fields) }}</dd>
        <dt>{{ t('dataAccess.mapping.incrementalField') }}</dt>
        <dd>{{ display(map.incremental_field) }}</dd>
        <dt>{{ t('dataAccess.mapping.matchKeys') }}</dt>
        <dd>{{ display(map.match_keys) }}</dd>
        <dt>{{ t('extractionUi.fusion') }}</dt>
        <dd>
          <pre>{{ display(map.fusion) }}</pre>
        </dd>
      </dl>
    </section>
    <section
      v-for="(map, index) in revision.rel_maps"
      :key="`relation-${index}`"
      class="mapping-section"
    >
      <h3>{{ map.relation_type }}</h3>
      <p>
        {{ t(`dataAccess.mapping.relationModes.${map.mode}`, String(map.mode)) }} ·
        <span class="mono">{{ `${map.schema}.${map.table}` }}</span>
      </p>
      <dl>
        <template v-if="map.mode === 'FK'"
          ><dt>{{ t('dataAccess.mapping.sourceField') }}</dt>
          <dd>{{ map.fk_field }}</dd></template
        >
        <template v-else>
          <dt>{{ t('extractionUi.sourceEndpoint') }}</dt>
          <dd>
            <pre>{{ display(map.source) }}</pre>
          </dd>
          <dt>{{ t('extractionUi.targetEndpoint') }}</dt>
          <dd>
            <pre>{{ display(map.target) }}</pre>
          </dd>
          <dt>{{ t('extractionUi.relationAttributes') }}</dt>
          <dd>
            <pre>{{ display(map.attributes) }}</pre>
          </dd>
        </template>
      </dl>
    </section>
    <NEmpty
      v-if="!revision.entity_maps.length && !revision.rel_maps.length"
      :description="t('dataAccess.mapping.noEntityMaps')"
    />
  </div>
</template>

<style scoped>
.frozen-mapping {
  display: grid;
  gap: 16px;
  min-width: 0;
}
.mapping-section {
  padding: 16px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-medium);
  min-width: 0;
}
h3 {
  margin: 0;
  font-size: 16px;
}
.table-scroll {
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th,
td {
  text-align: left;
  padding: 12px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}
th,
dt {
  color: var(--text-secondary);
}
dl {
  display: grid;
  grid-template-columns: minmax(100px, 160px) minmax(0, 1fr);
  gap: 12px;
}
dd {
  margin: 0;
  overflow-wrap: anywhere;
}
pre {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font: 12px var(--font-mono);
}
</style>
