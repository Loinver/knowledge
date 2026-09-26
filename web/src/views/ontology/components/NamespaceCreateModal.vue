<script setup lang="ts">
import type { FormInst, FormRules } from 'naive-ui'
import { NAlert, NButton, NForm, NFormItem, NInput, NModal } from 'naive-ui'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Namespace } from '@/api/namespaces'
import { namespacesApi } from '@/api/namespaces'
import { useApiError } from '@/composables/useApiError'

/**
 * 登记命名空间。命名空间管理页与实体/关系类型的新建抽屉共用：
 * 空库时新建抽屉里的命名空间下拉为空，必须能就地登记，否则建模第一步就走不通。
 */
const show = defineModel<boolean>('show', { required: true })
const emit = defineEmits<{ created: [namespace: Namespace] }>()

const { t } = useI18n()
const { toMessage } = useApiError()

/** 与后端 iri_service.PREFIX_PATTERN、app.iri.NAMESPACE_PATTERN 保持一致。 */
const PREFIX_PATTERN = /^[a-z][a-z0-9_-]{0,63}$/
const IRI_PATTERN = /^https?:\/\/[^\s<>"']+[#/]$/

const empty = () => ({ prefix: '', iri: '', labelZh: '', labelEn: '' })
const form = ref(empty())
const formRef = ref<FormInst | null>(null)
const saving = ref(false)
const error = ref('')

const rules = computed<FormRules>(() => ({
  prefix: [
    { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
    { pattern: PREFIX_PATTERN, message: t('namespace.prefixPattern'), trigger: ['blur', 'input'] },
  ],
  iri: [
    { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
    { pattern: IRI_PATTERN, message: t('namespace.iriPattern'), trigger: ['blur', 'input'] },
  ],
}))

function failText(err: unknown): string {
  const body = err as { code?: string; params?: { field?: string } } | undefined
  if (body?.code === 'KG.ALREADY_EXISTS') {
    return body.params?.field === 'iri'
      ? t('namespace.duplicateIri')
      : t('namespace.duplicatePrefix')
  }
  return toMessage(err)
}

async function submit() {
  error.value = ''
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const labels: Record<string, string> = {}
    if (form.value.labelZh.trim()) labels['zh-CN'] = form.value.labelZh.trim()
    if (form.value.labelEn.trim()) labels['en-US'] = form.value.labelEn.trim()
    const created = await namespacesApi.create({
      prefix: form.value.prefix.trim(),
      iri: form.value.iri.trim(),
      protected: false,
      label_i18n: Object.keys(labels).length ? labels : null,
    })
    emit('created', created)
    show.value = false
  } catch (err) {
    error.value = failText(err)
  } finally {
    saving.value = false
  }
}

watch(show, (open) => {
  if (!open) return
  form.value = empty()
  error.value = ''
  formRef.value?.restoreValidation()
})
</script>

<template>
  <NModal
    v-model:show="show"
    preset="card"
    :title="t('namespace.create')"
    :style="{ width: 'min(480px, calc(100vw - 32px))' }"
    :mask-closable="!saving"
  >
    <NForm
      ref="formRef"
      :model="form"
      :rules="rules"
      :disabled="saving"
      label-placement="top"
      @submit.prevent="submit"
    >
      <NFormItem :label="t('namespace.prefix')" path="prefix">
        <NInput v-model:value="form.prefix" placeholder="kg" />
        <template #feedback>{{ t('namespace.prefixHint') }}</template>
      </NFormItem>
      <NFormItem :label="t('namespace.iri')" path="iri">
        <NInput v-model:value="form.iri" placeholder="https://example.org/kg#" />
        <template #feedback>{{ t('namespace.iriHint') }}</template>
      </NFormItem>
      <NFormItem :label="t('common.labelZh')" path="labelZh">
        <NInput v-model:value="form.labelZh" />
      </NFormItem>
      <NFormItem :label="t('common.labelEn')" path="labelEn">
        <NInput v-model:value="form.labelEn" />
      </NFormItem>
    </NForm>
    <NAlert v-if="error" type="error" class="error">{{ error }}</NAlert>
    <template #footer>
      <div class="actions">
        <NButton :disabled="saving" @click="show = false">{{ t('common.cancel') }}</NButton>
        <NButton type="primary" :loading="saving" @click="submit">{{ t('common.save') }}</NButton>
      </div>
    </template>
  </NModal>
</template>

<style scoped>
.error {
  margin-top: var(--space-2);
}

.actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
}
</style>
