<script setup lang="ts">
import { NAlert, NButton, NInput, NSelect, NSpace, NTable } from 'naive-ui'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { clausesApi } from '@/api/clauses'
import { type CoreCheckRequest, type CoreCheckResult, templatesApi } from '@/api/templates'
import { useApiError } from '@/composables/useApiError'
import { useAsyncData } from '@/composables/useAsyncData'

const props = defineProps<{ templateId: number }>()
const { t } = useI18n()
const { toMessage } = useApiError()
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
  if (!canCheck.value || loading.value) return
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
  <NSpace vertical>
    <NAlert type="info">{{ t('coreCheck.hint') }}</NAlert>
    <NAlert v-if="clauses.error.value || error" type="error">{{
      clauses.error.value || error
    }}</NAlert>
    <NButton v-if="clauses.error.value" @click="clauses.reload">{{ t('graph.refresh') }}</NButton>
    <NSpace v-for="(item, index) in requirements" :key="index" vertical>
      <NInput
        v-model:value="item.name"
        :input-props="{ 'aria-label': t('common.name') }"
        :placeholder="t('common.name')"
      />
      <NSelect v-model:value="item.kind" :options="kinds" :aria-label="t('coreCheck.kind')" />
      <NSelect
        v-model:value="item.standard_clause_id"
        :options="options"
        filterable
        :loading="clauses.loading.value"
        :aria-label="t('coreCheck.clause')"
        :placeholder="t('coreCheck.clause')"
      />
      <NButton :disabled="requirements.length === 1" @click="requirements.splice(index, 1)">{{
        t('common.delete')
      }}</NButton>
    </NSpace>
    <NSpace>
      <NButton @click="requirements.push({ name: '', kind: 'ENTITY', standard_clause_id: null })">{{
        t('coreCheck.add')
      }}</NButton>
      <NButton
        type="primary"
        :disabled="!canCheck || !!clauses.error.value"
        :loading="loading"
        @click="check"
        >{{ t('coreCheck.run') }}</NButton
      >
    </NSpace>
    <template v-if="result">
      <NAlert :type="result.all_core_present ? 'success' : 'warning'">{{
        t(result.all_core_present ? 'coreCheck.present' : 'coreCheck.missing', {
          revision: result.template_revision,
        })
      }}</NAlert>
      <NTable size="small">
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
      </NTable>
    </template>
  </NSpace>
</template>
