<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteLeave } from 'vue-router'

import { authApi } from '@/api/auth'
import { getSessionGeneration } from '@/api/tokens'
import PageHeader from '@/components/PageHeader.vue'
import type { FormInst, FormRules } from '@/components/ui'
import { FormContainer, FormField, UiAlert, UiButton, UiInput, useMessage } from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useOwnedMutation } from '@/composables/useOwnedMutation'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const auth = useAuthStore()
const message = useMessage()
const { toMessage } = useApiError()

const formRef = ref<FormInst | null>(null)
const model = ref({ old_password: '', new_password: '', confirm: '' })
const mutation = useOwnedMutation(() => auth.user?.id, toMessage)
const { error, busy: saving } = mutation
let alive = true
let formVersion = 0
onBeforeUnmount(() => {
  alive = false
  formVersion++
})
watch(
  () => auth.user?.id,
  () => {
    formVersion++
    model.value = { old_password: '', new_password: '', confirm: '' }
    mutation.invalidate()
    formRef.value?.restoreValidation()
  },
  { flush: 'sync' },
)
onBeforeRouteLeave(
  () =>
    !auth.user ||
    !Object.values(model.value).some(Boolean) ||
    typeof window === 'undefined' ||
    window.confirm(t('ui.unsaved')),
)

const rules = computed<FormRules>(() => ({
  old_password: {
    required: true,
    message: t('account.rules.oldPasswordRequired'),
    trigger: ['blur', 'input'],
  },
  new_password: [
    { required: true, message: t('auth.rules.passwordRequired'), trigger: ['blur', 'input'] },
    { min: 8, message: t('auth.rules.passwordMin'), trigger: ['blur', 'input'] },
  ],
  confirm: [
    {
      validator: (_rule, value) => value === model.value.new_password,
      message: t('auth.rules.passwordMismatch'),
      trigger: ['blur', 'input'],
    },
  ],
}))

async function submit() {
  if (!alive || !formRef.value || saving.value || !auth.user) return
  const generation = getSessionGeneration()
  const version = formVersion
  const userId = auth.user.id
  mutation.invalidate()
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  if (
    !alive ||
    version !== formVersion ||
    generation !== getSessionGeneration() ||
    auth.user?.id !== userId ||
    saving.value
  )
    return
  const changed = await mutation.run(async () => {
    await authApi.changePassword({
      old_password: model.value.old_password,
      new_password: model.value.new_password,
    })
    return true
  })
  if (
    !changed ||
    !alive ||
    version !== formVersion ||
    generation !== getSessionGeneration() ||
    auth.user?.id !== userId
  )
    return
  model.value = { old_password: '', new_password: '', confirm: '' }
  formRef.value?.restoreValidation()
  message.success(t('account.passwordChanged'))
}
</script>

<template>
  <section class="account-page">
    <PageHeader :title="t('account.security')" :description="t('account.securityHint')" />
    <UiAlert v-if="error" type="error" role="alert" class="alert">{{ error }}</UiAlert>

    <div class="account-workspace">
      <aside class="identity-panel">
        <header class="group-heading">
          <span>{{ t('operationsUi.identity') }}</span>
          <h2>{{ t('account.currentSession') }}</h2>
        </header>
        <dl class="identity-list">
          <div>
            <dt>{{ t('auth.username') }}</dt>
            <dd class="mono">{{ auth.user?.username ?? t('common.noneValue') }}</dd>
          </div>
          <div>
            <dt>{{ t('account.role') }}</dt>
            <dd>{{ t(`account.roles.${auth.user?.role ?? 'VIEWER'}`) }}</dd>
          </div>
        </dl>
        <details class="session-help">
          <summary>{{ t('account.tokenStorage') }}</summary>
          <p>{{ t('account.tokenStorageHint') }}</p>
        </details>
      </aside>

      <section class="settings-panel">
        <header class="group-heading">
          <h2>{{ t('account.changePassword') }}</h2>
          <p>{{ t('account.securityHint') }}</p>
        </header>
        <FormContainer
          ref="formRef"
          class="settings-form"
          :model="model"
          :rules="rules"
          :submitting="saving"
          :disabled="!auth.user"
          label-placement="top"
          @submit="submit"
        >
          <FormField :label="t('account.oldPassword')" path="old_password">
            <UiInput
              v-model:value="model.old_password"
              type="password"
              show-password-on="click"
              autocomplete="current-password"
            />
          </FormField>
          <FormField :label="t('auth.newPassword')" path="new_password">
            <UiInput
              v-model:value="model.new_password"
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
          <div class="form-actions">
            <UiButton type="primary" attr-type="submit" :loading="saving" :disabled="!auth.user">
              {{ t('account.changePassword') }}
            </UiButton>
          </div>
        </FormContainer>
      </section>
    </div>
  </section>
</template>

<style scoped src="./AccountSettings.css"></style>
