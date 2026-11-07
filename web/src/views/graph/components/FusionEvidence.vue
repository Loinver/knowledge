<script setup lang="ts">
import { NAlert, NCard } from 'naive-ui'
import { useI18n } from 'vue-i18n'

import type { EntityFusion } from '@/api/graph'

defineProps<{ data: EntityFusion }>()
const { t } = useI18n()
function valueText(value: unknown): string {
  return value === null ? t('fusion.nullValue') : (JSON.stringify(value) ?? t('fusion.noValue'))
}
</script>

<template>
  <NCard :title="t('fusion.evidenceTitle')" class="fusion-evidence" data-testid="fusion-evidence">
    <NAlert v-if="data.evidence_state !== 'AVAILABLE'" type="warning">
      {{
        t(data.evidence_state === 'LEGACY' ? 'fusion.legacyEvidence' : 'fusion.unavailableEvidence')
      }}
    </NAlert>
    <template v-else>
      <p>
        {{
          t('fusion.runVersion', {
            run: data.run_id,
            mapping: data.mapping_revision_id,
            graph: data.graph_revision_id,
          })
        }}
      </p>
      <NAlert v-if="data.entity_state === 'QUARANTINED'" type="warning">{{
        t('fusion.entityQuarantined')
      }}</NAlert>
      <article
        v-for="decision in data.attributes"
        :key="decision.attribute"
        class="attribute-decision"
        data-testid="fusion-attribute"
        :data-attribute="decision.attribute"
      >
        <h3>{{ decision.attribute }}</h3>
        <p>
          <strong>{{ t('fusion.finalValue') }}</strong>
          {{ decision.final_value_present ? valueText(decision.final_value) : t('fusion.noValue') }}
        </p>
        <p>{{ t('fusion.reasonLabel') }} {{ t(`fusion.reason.${decision.reason}`) }}</p>
        <p class="muted">
          {{ t(`fusion.null.${decision.null_policy}`) }} ·
          {{ t(`fusion.conflict.${decision.conflict_policy}`) }}
        </p>
        <div
          class="candidate-scroll"
          tabindex="0"
          :aria-label="t('fusion.candidates', { attribute: decision.attribute })"
        >
          <table>
            <caption>
              {{
                t('fusion.candidates', { attribute: decision.attribute })
              }}
            </caption>
            <thead>
              <tr>
                <th>{{ t('fusion.source') }}</th>
                <th>{{ t('fusion.priority') }}</th>
                <th>{{ t('fusion.inputValue') }}</th>
                <th>{{ t('fusion.mappedValue') }}</th>
                <th>{{ t('fusion.candidateState') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(candidate, index) in decision.candidates" :key="index">
                <td>
                  <span
                    >{{ candidate.source_id }} ·
                    {{ `${candidate.schema_name}.${candidate.table_name}` }}</span
                  >
                  <br /><span>{{ candidate.row_key }} · {{ candidate.column }}</span>
                  <p v-if="candidate.occurrences > 1">
                    {{ t('fusion.occurrences', { n: candidate.occurrences }) }}
                  </p>
                </td>
                <td>{{ candidate.priority }}</td>
                <td>{{ valueText(candidate.input_value) }}</td>
                <td>
                  {{
                    candidate.state === 'SKIPPED' || candidate.state === 'INVALID'
                      ? t('fusion.noValue')
                      : valueText(candidate.value)
                  }}
                </td>
                <td>
                  {{
                    candidate.selected
                      ? t('fusion.selected')
                      : t(`fusion.candidate.${candidate.state}`)
                  }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </template>
  </NCard>
</template>

<style scoped>
.attribute-decision {
  padding-block: 16px;
  border-bottom: 1px solid var(--border);
}
.attribute-decision:last-child {
  border-bottom: 0;
}
.attribute-decision h3 {
  margin-top: 0;
}
.candidate-scroll {
  overflow: auto;
  margin-top: 12px;
}
.candidate-scroll:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}
table {
  width: 100%;
  border-collapse: collapse;
  min-width: 600px;
}
th,
td {
  text-align: left;
  padding: 10px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
  overflow-wrap: anywhere;
  max-width: 280px;
}
caption,
.muted {
  color: var(--text-secondary);
  text-align: left;
}
</style>
