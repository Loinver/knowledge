<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { clausesApi } from '@/api/clauses'
import { type CoreCheckRequest, type CoreCheckResult, templatesApi } from '@/api/templates'
import {
  FormContainer,
  FormField,
  UiAlert,
  UiButton,
  UiInput,
  UiSelect,
  UiSpace,
  UiTable,
  UiTag,
} from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useAssetAccess } from '@/composables/useAssetAccess'
import { useAsyncData } from '@/composables/useAsyncData'

const props = defineProps<{ templateId: number }>()
const { t } = useI18n()
const { toMessage } = useApiError()
const { canWrite } = useAssetAccess()
type Requirement = CoreCheckRequest['requirements'][number]
const requirements = ref<
  Array<Omit<Requirement, 'standard_clause_id'> & { standard_clause_id: number | null }>
>([{ name: '', kind: 'ENTITY', standard_clause_id: null }])
const clauses = useAsyncData((signal) => clausesApi.all(signal))
const options = computed(() =>
  (clauses.data.value ?? []).map((item) => ({
    value: item.id,
    label: `${item.standard} · ${item.clause_number}`,
  })),
)
const kinds = computed(() =>
  ['ENTITY', 'OBJECT_PROP', 'DATATYPE_PROP', 'ASSOC'].map((value) => ({
    value,
    label: t(`coreCheck.kinds.${value}`),
  })),
)
const result = ref<CoreCheckResult | null>(null)
const error = ref('')
const loading = ref(false)
let generation = 0
const controller = new AbortController()
onBeforeUnmount(() => controller.abort())
watch(
  [requirements, () => props.templateId],
  () => {
    generation++
    result.value = null
    error.value = ''
    loading.value = false
  },
  { deep: true, flush: 'sync' },
)
const canCheck = computed(
  () =>
    requirements.value.length > 0 &&
    requirements.value.every((item) => item.name.trim() && item.standard_clause_id),
)
async function check() {
  if (
    !canWrite.value ||
    !canCheck.value ||
    loading.value ||
    clauses.loading.value ||
    clauses.error.value
  )
    return
  const current = ++generation
  loading.value = true
  error.value = ''
  result.value = null
  try {
    const response = await templatesApi.coreCheck(
      props.templateId,
      {
        requirements: requirements.value.map((item) => ({
          ...item,
          name: item.name.trim(),
          standard_clause_id: item.standard_clause_id!,
        })),
      },
      controller.signal,
    )
    if (!controller.signal.aborted && current === generation) result.value = response
  } catch (cause) {
    if (!controller.signal.aborted && current === generation) error.value = toMessage(cause)
  } finally {
    if (current === generation) loading.value = false
  }
}
</script>

<template>
  <UiSpace vertical>
    <UiAlert v-if="!canWrite" type="info">{{ t('governanceUi.checkReadOnly') }}</UiAlert>
    <UiAlert type="info">{{ t('coreCheck.hint') }}</UiAlert>
    <UiAlert v-if="clauses.error.value || error" type="error">{{
      clauses.error.value || error
    }}</UiAlert>
    <UiButton v-if="clauses.error.value" @click="clauses.reload">{{ t('graph.refresh') }}</UiButton>
    <FormContainer
      :model="requirements"
      :disabled="!canWrite"
      :submitting="loading"
      :readonly="!canWrite"
      @submit="check"
    >
      <div v-for="(item, index) in requirements" :key="index" class="requirement-row">
        <FormField :label="t('common.name')"
          ><UiInput
            v-model:value="item.name"
            :disabled="!canWrite || loading"
            :input-props="{ 'aria-label': t('common.name') }"
            :placeholder="t('common.name')"
          /> </FormField
        ><FormField :label="t('coreCheck.kind')"
          ><UiSelect
            v-model:value="item.kind"
            :disabled="!canWrite || loading"
            :options="kinds"
            :aria-label="t('coreCheck.kind')"
          /> </FormField
        ><FormField :label="t('coreCheck.clause')"
          ><UiSelect
            v-model:value="item.standard_clause_id"
            :disabled="!canWrite || loading"
            :options="options"
            filterable
            :loading="clauses.loading.value"
            :aria-label="t('coreCheck.clause')"
            :placeholder="t('coreCheck.clause')"
          /> </FormField
        ><UiButton
          :disabled="!canWrite || loading || requirements.length === 1"
          @click="requirements.splice(index, 1)"
          >{{ t('common.delete') }}</UiButton
        >
      </div>
    </FormContainer>
    <UiSpace>
      <UiButton
        :disabled="!canWrite || loading"
        @click="requirements.push({ name: '', kind: 'ENTITY', standard_clause_id: null })"
        >{{ t('coreCheck.add') }}</UiButton
      >
      <UiButton
        type="primary"
        :disabled="!canWrite || !canCheck || clauses.loading.value || !!clauses.error.value"
        :loading="loading"
        @click="check"
        >{{ t('coreCheck.run') }}</UiButton
      >
    </UiSpace>
    <template v-if="result">
      <UiAlert
        :type="
          result.standards_conformance === 'VIOLATION'
            ? 'error'
            : result.all_core_present
              ? 'info'
              : 'warning'
        "
        >{{
          t(result.all_core_present ? 'coreCheck.present' : 'coreCheck.missing', {
            revision: result.template_revision,
          })
        }}</UiAlert
      >
      <UiTag :type="result.standards_conformance === 'VIOLATION' ? 'error' : 'default'">
        {{ t('entityType.validationState') }} ·
        {{ t(`validation.${result.standards_conformance}`) }}
      </UiTag>
      <UiTable size="small">
        <thead>
          <tr>
            <th>{{ t('common.name') }}</th>
            <th>{{ t('common.status') }}</th>
            <th>{{ t('common.revision') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, index) in result.items" :key="index">
            <td>{{ item.name }}</td>
            <td>{{ t(`coreCheck.states.${item.state}`) }}</td>
            <td>{{ item.pinned_revision ?? '—' }}</td>
          </tr>
        </tbody>
      </UiTable>
    </template>
  </UiSpace>
</template>

<style scoped>
.requirement-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 150px minmax(0, 1.2fr) auto;
  gap: 12px;
  align-items: center;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-inset);
}
.requirement-row :deep(.ui-field) {
  min-width: 0;
}
@media (max-width: 768px) {
  .requirement-row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
