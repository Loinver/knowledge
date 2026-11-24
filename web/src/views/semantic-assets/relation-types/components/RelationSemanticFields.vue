<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { RelationTypeDetail } from '@/api/relations'
import { FormField, UiCheckbox, UiInput, UiInputNumber, UiSelect, UiSpace } from '@/components/ui'

type Cardinality = NonNullable<RelationTypeDetail['domain_spec']['cardinality']>
const definitionZh = defineModel<string>('definitionZh', { required: true })
const definitionEn = defineModel<string>('definitionEn', { required: true })
const domainCardinality = defineModel<Cardinality>('domainCardinality', { required: true })
const rangeCardinality = defineModel<Cardinality>('rangeCardinality', { required: true })
const inverseOf = defineModel<number | null>('inverseOf', { required: true })
const owl = defineModel<RelationTypeDetail['owl']>('owl', { required: true })
defineProps<{
  inverseOptions: { label: string; value: number }[]
  referencesLoading: boolean
}>()
const { t } = useI18n()

function setBound(side: 'domain' | 'range', key: 'min' | 'max', value: number | null) {
  if (value === null) return
  const model = side === 'domain' ? domainCardinality : rangeCardinality
  model.value = { ...model.value, [key]: value }
}
</script>

<template>
  <fieldset class="semantic-section">
    <legend>{{ t('common.definition') }}</legend>
    <FormField :label="t('common.definitionZh')" path="definitionZh">
      <UiInput
        v-model:value="definitionZh"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 4 }"
      />
    </FormField>
    <FormField :label="t('common.definitionEn')" path="definitionEn">
      <UiInput
        v-model:value="definitionEn"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 4 }"
      />
    </FormField>
  </fieldset>
  <fieldset class="semantic-section">
    <legend>{{ t('relationDetail.endpoints') }}</legend>
    <div class="cardinality-grid">
      <fieldset class="cardinality-side">
        <legend>{{ t('relation.domainCardinality') }}</legend>
        <UiSpace vertical>
          <div class="cardinality-bounds">
            <FormField :label="t('relation.minCard')" path="domainCardinality.min">
              <UiInputNumber
                :value="domainCardinality.min"
                :min="0"
                :precision="0"
                :clearable="false"
                :aria-label="t('relation.minCard')"
                @update:value="setBound('domain', 'min', $event)"
              />
            </FormField>
            <FormField :label="t('relation.maxCard')" path="domainCardinality.max">
              <UiInputNumber
                :value="domainCardinality.max"
                :min="-1"
                :precision="0"
                :clearable="false"
                :aria-label="t('relation.maxCard')"
                @update:value="setBound('domain', 'max', $event)"
              />
            </FormField>
          </div>
          <span>{{ t('relation.domainCardinalityHint') }}</span>
        </UiSpace>
      </fieldset>
      <fieldset class="cardinality-side">
        <legend>{{ t('relation.rangeCardinality') }}</legend>
        <UiSpace vertical>
          <div class="cardinality-bounds">
            <FormField :label="t('relation.minCard')" path="rangeCardinality.min">
              <UiInputNumber
                :value="rangeCardinality.min"
                :min="0"
                :precision="0"
                :clearable="false"
                :aria-label="t('relation.minCard')"
                @update:value="setBound('range', 'min', $event)"
              />
            </FormField>
            <FormField :label="t('relation.maxCard')" path="rangeCardinality.max">
              <UiInputNumber
                :value="rangeCardinality.max"
                :min="-1"
                :precision="0"
                :clearable="false"
                :aria-label="t('relation.maxCard')"
                @update:value="setBound('range', 'max', $event)"
              />
            </FormField>
          </div>
          <span>{{ t('relation.rangeCardinalityHint') }}</span>
        </UiSpace>
      </fieldset>
    </div>
  </fieldset>
  <fieldset class="semantic-section">
    <legend>{{ t('relation.owl') }}</legend>
    <FormField :label="t('relation.inverseOf')" path="inverseOf">
      <UiSelect
        v-model:value="inverseOf"
        :options="inverseOptions"
        :loading="referencesLoading"
        filterable
        clearable
      />
    </FormField>
    <UiSpace vertical>
      <FormField path="owl.functional" :show-feedback="false">
        <UiCheckbox v-model:checked="owl.functional">{{ t('relation.functional') }}</UiCheckbox>
      </FormField>
      <FormField path="owl.inverse_functional" :show-feedback="false">
        <UiCheckbox v-model:checked="owl.inverse_functional">{{
          t('relation.inverseFunctional')
        }}</UiCheckbox>
      </FormField>
      <FormField path="owl.symmetric" :show-feedback="false">
        <UiCheckbox v-model:checked="owl.symmetric">{{ t('relation.symmetric') }}</UiCheckbox>
      </FormField>
      <FormField path="owl.transitive" :show-feedback="false">
        <UiCheckbox v-model:checked="owl.transitive">{{ t('relation.transitive') }}</UiCheckbox>
      </FormField>
      <span>{{ t('relation.owlHint') }}</span>
    </UiSpace>
  </fieldset>
</template>

<style scoped>
.semantic-section {
  min-width: 0;
  margin: 0 0 16px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-panel);
  grid-column: 1 / -1;
}
legend {
  padding: 0 6px;
  font-size: 12px;
  color: var(--text-secondary);
}
.cardinality-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.cardinality-side {
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}
.cardinality-bounds {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-2);
}
.semantic-section :deep(.ui-field) {
  min-width: 0;
}
.semantic-section :deep(.ui-number-input) {
  max-width: 100%;
}
@media (max-width: 640px) {
  .cardinality-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
