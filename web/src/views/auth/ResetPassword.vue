<script setup lang="ts">
import type { FormInst, FormRules } from 'naive-ui'
import { NAlert, NButton, NForm, NFormItem, NInput } from 'naive-ui'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { authApi } from '@/api/auth'
import { useApiError } from '@/composables/useApiError'
import AuthHeading from '@/views/auth/AuthHeading.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { toMessage } = useApiError()

const formRef = ref<FormInst | null>(null)
const model = ref({ password: '', confirm: '' })
const error = ref('')
const loading = ref(false)

const token = computed(() => (typeof route.query.token === 'string' ? route.query.token : ''))

const rules = computed<FormRules>(() => ({
  password: [
    { required: true, message: t('auth.rules.passwordRequired'), trigger: ['blur', 'input'] },
    { min: 8, message: t('auth.rules.passwordMin'), trigger: ['blur', 'input'] },
  ],
  confirm: [
    {
      validator: (_rule, value: string) => value === model.value.password,
      message: t('auth.rules.passwordMismatch'),
      trigger: ['blur', 'input'],
    },
  ],
}))

async function submit() {
  error.value = ''
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await authApi.resetPassword(token.value, model.value.password)
    await router.replace({ name: 'login' })
  } catch (err) {
    error.value = toMessage(err)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <NForm ref="formRef" :model="model" :rules="rules" label-placement="top" @submit.prevent="submit">
    <AuthHeading :title="t('auth.resetTitle')" :subtitle="t('auth.resetHint')" />
    <NAlert v-if="!token" type="warning" role="alert" class="form-alert">
      {{ t('auth.resetTokenMissing') }}
    </NAlert>
    <NAlert v-if="error" type="error" role="alert" class="form-alert">{{ error }}</NAlert>
    <NFormItem :label="t('auth.newPassword')" path="password">
      <NInput
        v-model:value="model.password"
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
    <NButton type="primary" block attr-type="submit" :loading="loading" :disabled="!token">
      {{ t('auth.resetSubmit') }}
    </NButton>
    <div class="form-links">
      <RouterLink :to="{ name: 'login' }">{{ t('auth.toLogin') }}</RouterLink>
    </div>
  </NForm>
</template>

<style scoped>
.form-alert {
  margin-bottom: var(--space-3);
}
.form-links {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--space-3);
  font-size: var(--font-small);
}
</style>
