<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteUpdate } from 'vue-router'

import { knowledgeApi, type KnowledgeBase } from '@/api/knowledge'
import type { FormInst, FormRules } from '@/components/ui'
import {
  FormActions,
  FormContainer,
  FormField,
  FormSection,
  SheetForm,
  UiAlert,
  UiButton,
  UiInput,
} from '@/components/ui'
import { useDraftGuard } from '@/composables/useDraftGuard'
import { useOwnedMutation } from '@/composables/useOwnedMutation'
import { useAuthStore } from '@/stores/auth'

import { useKnowledgeMessage } from '../composables/useKnowledge'

const props = defineProps<{ show: boolean; base?: KnowledgeBase | null }>()
const emit = defineEmits<{ 'update:show': [value: boolean]; saved: [value: KnowledgeBase] }>()
const { t } = useI18n()
const auth = useAuthStore()
const canWrite = computed(() => ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? ''))
const { message } = useKnowledgeMessage()
const open = ref(false)
const form = ref({ name: '', description: '' })
const formRef = ref<FormInst | null>(null)
const target = shallowRef<KnowledgeBase | null>(null)
const session = ref(0)
watch(
  () => [props.show, props.base?.id ?? null] as const,
  ([show, id], previous) => {
    if (previous && previous[0] === show && previous[1] === id) return
    session.value++
    if (show) {
      target.value = props.base ? { ...props.base } : null
      form.value = { name: target.value?.name ?? '', description: target.value?.description ?? '' }
    }
    open.value = show
  },
  { immediate: true, flush: 'sync' },
)
watch(open, (show) => emit('update:show', show))
const guarded = useDraftGuard(
  open,
  () => form.value,
  () => true,
  () => session.value,
)
const { busy, error, run } = useOwnedMutation(
  () => [open.value, session.value, target.value?.id, target.value?.revision, canWrite.value],
  (error) =>
    error instanceof Error && ['FORM_INVALID', 'FORM_CONTEXT_CHANGED'].includes(error.message)
      ? ''
      : message(error),
)
const visible = computed({
  get: () => guarded.value,
  set: (value: boolean) => {
    if (!busy.value) guarded.value = value
  },
})
const rules = computed<FormRules>(() => ({
  name: [
    { required: true, message: t('common.required') },
    { max: 200, message: t('ds.form.maxLength', { max: 200 }) },
  ],
  description: { max: 4000, message: t('ds.form.maxLength', { max: 4000 }) },
}))
onBeforeRouteUpdate((to, from) => {
  if (to.params.id !== from.params.id) {
    visible.value = false
    return !open.value
  }
  return true
})
async function save() {
  if (!canWrite.value || busy.value || !open.value || !formRef.value) return
  const payload = { name: form.value.name.trim(), description: form.value.description }
  const current = target.value
  const result = await run(async (signal) => {
    await formRef.value!.validate()
    if (signal.aborted || !canWrite.value) throw new Error('FORM_CONTEXT_CHANGED')
    return current
      ? knowledgeApi.update(current.id, payload, current.revision, signal)
      : knowledgeApi.create(payload, signal)
  })
  if (result) {
    open.value = false
    emit('saved', result)
  }
}
</script>
<template>
  <SheetForm
    v-model:show="visible"
    width="min(480px,100vw)"
    :title="t(target ? 'kb.edit' : 'kb.create')"
    :submitting="busy"
  >
    <div class="kb-stack kb-inspector-content">
      <UiAlert type="info">{{ t('kb.globalAccess') }}</UiAlert>
      <UiAlert v-if="error" type="error" role="alert">{{ error }}</UiAlert>
      <FormContainer
        id="kb-editor-form"
        ref="formRef"
        :model="form"
        :rules="rules"
        :disabled="busy || !canWrite"
        @submit="save"
      >
        <FormSection :title="t('kb.detail')">
          <FormField path="name" :label="t('kb.name')" required>
            <UiInput v-model:value="form.name" :maxlength="200" />
          </FormField>
          <FormField path="description" :label="t('kb.description')">
            <UiInput
              v-model:value="form.description"
              type="textarea"
              :maxlength="4000"
              :autosize="{ minRows: 4, maxRows: 10 }"
            />
          </FormField>
        </FormSection>
      </FormContainer>
    </div>
    <template #actions
      ><FormActions :submitting="busy">
        <UiButton :disabled="busy" @click="visible = false">{{ t('common.cancel') }}</UiButton>
        <UiButton
          type="primary"
          attr-type="submit"
          form="kb-editor-form"
          :disabled="!canWrite"
          :loading="busy"
          >{{ t('common.save') }}</UiButton
        >
      </FormActions></template
    >
  </SheetForm>
</template>
