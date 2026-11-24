<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { FusionPolicy } from '@/api/mappings'
import { FormField, UiAlert, UiInputNumber, UiSelect } from '@/components/ui'

const props = defineProps<{ modelValue: FusionPolicy | null; disabled?: boolean; path?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: FusionPolicy | null] }>()
const { t } = useI18n()
const priority = ref<number | null>(null)
const nullPolicy = ref<FusionPolicy['null_policy'] | null>(null)
const conflictPolicy = ref<FusionPolicy['conflict_policy'] | null>(null)
watch(
  () => props.modelValue,
  (value) => {
    priority.value = value?.priority ?? null
    nullPolicy.value = value?.null_policy ?? null
    conflictPolicy.value = value?.conflict_policy ?? null
  },
  { immediate: true },
)
function update() {
  emit(
    'update:modelValue',
    priority.value !== null && nullPolicy.value !== null && conflictPolicy.value !== null
      ? {
          priority: priority.value,
          null_policy: nullPolicy.value,
          conflict_policy: conflictPolicy.value,
        }
      : null,
  )
}
</script>

<template>
  <fieldset class="fusion-policy" data-testid="fusion-policy">
    <legend>{{ t('fusion.policyTitle') }}</legend>
    <p>{{ t('fusion.policyHint') }}</p>
    <UiAlert v-if="!modelValue" type="warning">{{
      t(disabled ? 'fusion.legacyPolicy' : 'fusion.policyRequired')
    }}</UiAlert>
    <div class="policy-fields">
      <FormField :path="path ? `${path}.priority` : undefined" :label="t('fusion.priority')">
        <UiInputNumber
          v-model:value="priority"
          data-testid="fusion-priority"
          :min="1"
          :max="1000000"
          :precision="0"
          :disabled="disabled"
          :input-props="{ 'aria-label': t('fusion.priority') }"
          @update:value="update"
        />
      </FormField>
      <FormField :path="path ? `${path}.null_policy` : undefined" :label="t('fusion.nullPolicy')">
        <UiSelect
          v-model:value="nullPolicy"
          data-testid="fusion-null-policy"
          :disabled="disabled"
          :aria-label="t('fusion.nullPolicy')"
          :options="
            ['IGNORE', 'KEEP'].map((value) => ({ value, label: t(`fusion.null.${value}`) }))
          "
          @update:value="update"
        />
      </FormField>
      <FormField
        :path="path ? `${path}.conflict_policy` : undefined"
        :label="t('fusion.conflictPolicy')"
      >
        <UiSelect
          v-model:value="conflictPolicy"
          data-testid="fusion-conflict-policy"
          :disabled="disabled"
          :aria-label="t('fusion.conflictPolicy')"
          :options="
            ['PRIORITY', 'QUARANTINE'].map((value) => ({
              value,
              label: t(`fusion.conflict.${value}`),
            }))
          "
          @update:value="update"
        />
      </FormField>
    </div>
    <p>{{ t('fusion.tieHint') }}</p>
  </fieldset>
</template>

<style scoped>
.fusion-policy {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  min-width: 0;
}
.fusion-policy p {
  color: var(--text-secondary);
  margin: 8px 0;
}
.policy-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin-top: 12px;
}
</style>
