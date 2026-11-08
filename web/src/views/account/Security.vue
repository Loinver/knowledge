<script setup lang="ts">
import type { FormInst, FormRules } from 'naive-ui'
import {
  NAlert,
  NButton,
  NCard,
  NDescriptions,
  NDescriptionsItem,
  NForm,
  NFormItem,
  NInput,
  useMessage,
} from 'naive-ui'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteLeave } from 'vue-router'

import { authApi } from '@/api/auth'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const auth = useAuthStore()
const message = useMessage()
const { toMessage } = useApiError()

const formRef = ref<FormInst | null>(null)
const model = ref({ old_password: '', new_password: '', confirm: '' })
const error = ref('')
const saving = ref(false)
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
      validator: (_rule, value: string) => value === model.value.new_password,
      message: t('auth.rules.passwordMismatch'),
      trigger: ['blur', 'input'],
    },
  ],
}))

async function submit() {
  if (saving.value || !auth.user) return
  error.value = ''
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  if (saving.value) return
  saving.value = true
  try {
    await authApi.changePassword({
      old_password: model.value.old_password,
      new_password: model.value.new_password,
    })
    model.value = { old_password: '', new_password: '', confirm: '' }
    formRef.value?.restoreValidation()
    message.success(t('account.passwordChanged'))
  } catch (err) {
    error.value = toMessage(err)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="account-page">
    <PageHeader :title="t('account.security')" :description="t('account.securityHint')" />
    <NAlert v-if="error" type="error" role="alert" class="alert">{{ error }}</NAlert>

    <NCard size="small" class="card" :title="t('account.currentSession')">
      <NDescriptions :column="1" bordered label-placement="left">
        <NDescriptionsItem :label="t('auth.username')">{{ auth.user?.username }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('account.role')">
          {{ t(`account.roles.${auth.user?.role ?? 'VIEWER'}`) }}
        </NDescriptionsItem>
      </NDescriptions>
    </NCard>

    <NCard size="small" class="card" :title="t('account.changePassword')">
      <NForm ref="formRef" :model="model" :rules="rules" label-placement="top">
        <NFormItem :label="t('account.oldPassword')" path="old_password">
          <NInput
            v-model:value="model.old_password"
            type="password"
            show-password-on="click"
            autocomplete="current-password"
          />
        </NFormItem>
        <NFormItem :label="t('auth.newPassword')" path="new_password">
          <NInput
            v-model:value="model.new_password"
            type="password"
            show-password-on="click"
            autocomplete="new-password"
          />
        </NFormItem>
        <NFormItem :label="t('auth.confirmPassword')" path="confirm">
          <NInput
            v-model:value="model.confirm"
            type="password"
            show-password-on="click"
            autocomplete="new-password"
            @keyup.enter="submit"
          />
        </NFormItem>
        <NButton type="primary" :loading="saving" :disabled="!auth.user" @click="submit">
          {{ t('account.changePassword') }}
        </NButton>
      </NForm>
    </NCard>
    <details class="session-help">
      <summary>{{ t('account.tokenStorage') }}</summary>
      <p>{{ t('account.tokenStorageHint') }}</p>
    </details>
  </section>
</template>

<style scoped>
.account-page {
  max-width: 760px;
}
.session-help {
  color: var(--text-secondary);
  font-size: 12px;
}
.session-help summary {
  cursor: pointer;
}
.alert,
.card {
  margin-bottom: var(--space-4);
}
</style>
