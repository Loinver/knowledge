<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Namespace } from '@/api/namespaces'
import { namespacesApi } from '@/api/namespaces'
import type { FormInst, FormRules } from '@/components/ui'
import { DialogForm, FormContainer, FormField, UiAlert, UiButton, UiInput } from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useDraftGuard } from '@/composables/useDraftGuard'
import { useOwnedMutation } from '@/composables/useOwnedMutation'
import { useAuthStore } from '@/stores/auth'

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
const session = ref(0)
const auth = useAuthStore()
const canWrite = computed(() => ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? ''))
const {
  busy: saving,
  error,
  run,
} = useOwnedMutation(
  () => [show.value, session.value],
  (error) =>
    error instanceof Error && ['FORM_INVALID', 'FORM_CONTEXT_CHANGED'].includes(error.message)
      ? ''
      : failText(error),
)
const editorVisible = useDraftGuard(
  show,
  () => form.value,
  () => true,
  () => session.value,
)

const rules = computed<FormRules>(() => ({
  prefix: [
    { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
    {
      validator: (_rule, value) => typeof value === 'string' && PREFIX_PATTERN.test(value.trim()),
      message: t('namespace.prefixPattern'),
      trigger: ['blur', 'input'],
    },
  ],
  iri: [
    { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
    {
      validator: (_rule, value) => typeof value === 'string' && IRI_PATTERN.test(value.trim()),
      message: t('namespace.iriPattern'),
      trigger: ['blur', 'input'],
    },
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
  if (saving.value || !show.value || !canWrite.value) return
  const draft = { ...form.value }
  const created = await run(async (signal) => {
    await formRef.value?.validate()
    if (signal.aborted) throw new Error('FORM_CONTEXT_CHANGED')
    const labels: Record<string, string> = {}
    if (draft.labelZh.trim()) labels['zh-CN'] = draft.labelZh.trim()
    if (draft.labelEn.trim()) labels['en-US'] = draft.labelEn.trim()
    return namespacesApi.create({
      prefix: draft.prefix.trim(),
      iri: draft.iri.trim(),
      protected: false,
      label_i18n: Object.keys(labels).length ? labels : null,
    })
  })
  if (created) {
    emit('created', created)
    show.value = false
  }
}

watch(
  show,
  (open) => {
    session.value++
    if (!open) return
    form.value = empty()
    formRef.value?.restoreValidation()
  },
  { flush: 'sync' },
)
</script>

<template>
  <DialogForm
    v-model:show="editorVisible"
    class="asset-editor"
    :title="t('namespace.create')"
    :style="{ width: 'min(480px, calc(100vw - 32px))' }"
    :submitting="saving"
  >
    <UiAlert v-if="!canWrite" type="info">{{ t('ui.readonly') }}</UiAlert>
    <FormContainer
      id="namespace-create-form"
      ref="formRef"
      :model="form"
      :rules="rules"
      :disabled="saving || !canWrite"
      label-placement="top"
      @submit.prevent="submit"
    >
      <fieldset class="form-section">
        <legend>{{ t('common.name') }}</legend>
        <FormField :label="t('namespace.prefix')" path="prefix">
          <UiInput v-model:value="form.prefix" placeholder="kg" />
          <template #feedback>{{ t('namespace.prefixHint') }}</template>
        </FormField>
        <FormField :label="t('namespace.iri')" path="iri">
          <UiInput v-model:value="form.iri" placeholder="https://example.org/kg#" />
          <template #feedback>{{ t('namespace.iriHint') }}</template>
        </FormField>
      </fieldset>
      <fieldset class="form-section">
        <legend>{{ t('common.label') }}</legend>
        <div class="form-grid">
          <FormField :label="t('common.labelZh')" path="labelZh">
            <UiInput v-model:value="form.labelZh" />
          </FormField>
          <FormField :label="t('common.labelEn')" path="labelEn">
            <UiInput v-model:value="form.labelEn" />
          </FormField>
        </div></fieldset
    ></FormContainer>
    <UiAlert v-if="error" type="error" class="error">{{ error }}</UiAlert>
    <template #actions>
      <div class="actions">
        <UiButton :disabled="saving" @click="editorVisible = false">{{
          t('common.cancel')
        }}</UiButton>
        <UiButton
          type="primary"
          attr-type="submit"
          form="namespace-create-form"
          :loading="saving"
          :disabled="!canWrite"
          >{{ t('common.save') }}</UiButton
        >
      </div>
    </template>
  </DialogForm>
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

<style scoped src="../styles/observatory.css"></style>
