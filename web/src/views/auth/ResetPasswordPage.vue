<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { authApi } from '@/api/auth'
import { getSessionGeneration } from '@/api/tokens'
import type { FormInst, FormRules } from '@/components/ui'
import { FormContainer, FormField, UiAlert, UiButton, UiInput } from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useOwnedMutation } from '@/composables/useOwnedMutation'
import AuthHeading from '@/views/auth/components/AuthHeading.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { toMessage } = useApiError()

const formRef = ref<FormInst | null>(null)
const model = ref({ password: '', confirm: '' })
const error = ref('')
const mutation = useOwnedMutation(() => [route.fullPath, getSessionGeneration()], toMessage)
const { busy: loading } = mutation
let alive = true
onBeforeUnmount(() => {
  alive = false
})

const token = computed(() => (typeof route.query.token === 'string' ? route.query.token : ''))
watch(
  token,
  () => {
    model.value = { password: '', confirm: '' }
    error.value = ''
    formRef.value?.restoreValidation()
  },
  { flush: 'sync' },
)

const rules = computed<FormRules>(() => ({
  password: [
    { required: true, message: t('auth.rules.passwordRequired'), trigger: ['blur', 'input'] },
    { min: 8, message: t('auth.rules.passwordMin'), trigger: ['blur', 'input'] },
  ],
  confirm: [
    {
      validator: (_rule, value) => value === model.value.password,
      message: t('auth.rules.passwordMismatch'),
      trigger: ['blur', 'input'],
    },
  ],
}))

async function submit() {
  if (!alive || !formRef.value || loading.value || !token.value) return
  const generation = getSessionGeneration()
  const path = route.fullPath
  const resetToken = token.value
  error.value = ''
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  if (
    !alive ||
    path !== route.fullPath ||
    generation !== getSessionGeneration() ||
    resetToken !== token.value ||
    loading.value
  )
    return
  const reset = await mutation.run(async () => {
    await authApi.resetPassword(resetToken, model.value.password)
    return true
  })
  if (!alive || path !== route.fullPath || generation !== getSessionGeneration()) return
  if (!reset) {
    error.value = mutation.error.value
    return
  }
  await router.replace({ name: 'login' })
}
</script>

<template>
  <FormContainer
    ref="formRef"
    class="auth-flow"
    :model="model"
    :rules="rules"
    :submitting="loading"
    :disabled="!token"
    label-placement="top"
    @submit="submit"
  >
    <AuthHeading :title="t('auth.resetTitle')" :subtitle="t('auth.resetHint')" />
    <UiAlert v-if="!token" type="warning" role="alert" class="form-alert">
      {{ t('auth.resetTokenMissing') }}
    </UiAlert>
    <UiAlert v-if="error" type="error" role="alert" class="form-alert">{{ error }}</UiAlert>
    <FormField :label="t('auth.newPassword')" path="password">
      <UiInput
        v-model:value="model.password"
        type="password"
        show-password-on="click"
        autocomplete="new-password"
      />
    </FormField>
    <FormField :label="t('auth.confirmPassword')" path="confirm">
      <UiInput
        v-model:value="model.confirm"
        type="password"
        show-password-on="click"
        autocomplete="new-password"
      />
    </FormField>
    <UiButton type="primary" block attr-type="submit" :loading="loading" :disabled="!token">
      {{ t('auth.resetSubmit') }}
    </UiButton>
    <div class="form-links">
      <RouterLink :to="{ name: 'login' }">{{ t('auth.toLogin') }}</RouterLink>
    </div>
  </FormContainer>
</template>

<style scoped src="./AuthForm.css"></style>
