<script setup lang="ts">
import type { FormInst, FormRules } from 'naive-ui'
import { NAlert, NButton, NForm, NFormItem, NInput } from 'naive-ui'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRouter } from 'vue-router'

import { authApi } from '@/api/auth'
import { useApiError } from '@/composables/useApiError'

const { t } = useI18n()
const router = useRouter()
const { toMessage } = useApiError()

const formRef = ref<FormInst | null>(null)
const model = ref({ email: '' })
const error = ref('')
const sent = ref(false)
const loading = ref(false)

const rules = computed<FormRules>(() => ({
  email: [
    { required: true, message: t('auth.rules.emailRequired'), trigger: ['blur', 'input'] },
    { type: 'email', message: t('auth.rules.emailPattern'), trigger: ['blur', 'input'] },
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
    const result = await authApi.forgotPassword(model.value.email)
    // 开发态没有邮件服务，后端把重置令牌放在响应里（生产为 null，由邮件送达）：
    // 拿到令牌就直接进重置页，省掉手工拷贝那一步。
    if (result.reset_token) {
      await router.replace({
        name: 'reset-password',
        query: { token: result.reset_token },
      })
      return
    }
    sent.value = true
  } catch (err) {
    error.value = toMessage(err)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <NForm ref="formRef" :model="model" :rules="rules" label-placement="top" @submit.prevent="submit">
    <h2 class="form-title">{{ t('auth.forgotTitle') }}</h2>
    <p class="form-hint">{{ t('auth.forgotHint') }}</p>
    <NAlert v-if="error" type="error" role="alert" class="form-alert">{{ error }}</NAlert>
    <NAlert v-if="sent" type="success" role="status" class="form-alert">
      {{ t('auth.forgotSent') }}
    </NAlert>
    <NFormItem :label="t('auth.email')" path="email">
      <NInput v-model:value="model.email" autocomplete="email" @keyup.enter="submit" />
    </NFormItem>
    <NButton type="primary" block attr-type="submit" :loading="loading">
      {{ t('auth.sendResetLink') }}
    </NButton>
    <div class="form-links">
      <RouterLink :to="{ name: 'login' }">{{ t('auth.toLogin') }}</RouterLink>
    </div>
  </NForm>
</template>

<style scoped>
.form-title {
  margin: 0 0 var(--space-2);
  font-size: 16px;
}
.form-hint {
  margin: 0 0 var(--space-4);
  color: var(--text-secondary);
  font-size: var(--font-small);
}
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
