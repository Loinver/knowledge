<script setup lang="ts">
import type { FormInst, FormRules } from 'naive-ui'
import { NAlert, NButton, NForm, NFormItem, NInput } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRouter } from 'vue-router'

import { authApi } from '@/api/auth'
import { useApiError } from '@/composables/useApiError'
import { useAuthStore } from '@/stores/auth'
import AuthHeading from '@/views/auth/AuthHeading.vue'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const { toMessage } = useApiError()

const formRef = ref<FormInst | null>(null)
const model = ref({ username: '', email: '', password: '', confirm: '' })
const error = ref('')

/**
 * 公开注册默认关闭：账号由管理员在「系统管理 → 用户管理」里发放。
 * `null` 表示配置还没回来，此时不渲染表单，避免闪一下再被拒绝。
 */
const registrationEnabled = ref<boolean | null>(null)
const passwordMin = ref(8)

onMounted(async () => {
  try {
    const config = await authApi.config()
    registrationEnabled.value = config.registration_enabled
    passwordMin.value = config.password_min_length
  } catch {
    registrationEnabled.value = false
  }
})

const rules = computed<FormRules>(() => ({
  username: [
    { required: true, message: t('auth.rules.usernameRequired'), trigger: ['blur', 'input'] },
    {
      pattern: /^[A-Za-z0-9_]{3,32}$/,
      message: t('auth.rules.usernamePattern'),
      trigger: ['blur', 'input'],
    },
  ],
  email: [
    { required: true, message: t('auth.rules.emailRequired'), trigger: ['blur', 'input'] },
    { type: 'email', message: t('auth.rules.emailPattern'), trigger: ['blur', 'input'] },
  ],
  password: [
    { required: true, message: t('auth.rules.passwordRequired'), trigger: ['blur', 'input'] },
    { min: passwordMin.value, message: t('auth.rules.passwordMin'), trigger: ['blur', 'input'] },
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
  try {
    await auth.register({
      username: model.value.username,
      email: model.value.email,
      password: model.value.password,
    })
    await router.replace({ name: 'dashboard' })
  } catch (err) {
    error.value = toMessage(err)
  }
}
</script>

<template>
  <div v-if="registrationEnabled === false" class="closed">
    <AuthHeading :title="t('auth.registerTitle')" :subtitle="t('auth.registerSubtitle')" />
    <NAlert type="warning" role="alert" class="form-alert">
      {{ t('auth.registrationClosed') }}
    </NAlert>
    <div class="form-links">
      <RouterLink :to="{ name: 'login' }">{{ t('auth.toLogin') }}</RouterLink>
    </div>
  </div>

  <NForm
    v-else-if="registrationEnabled"
    ref="formRef"
    :model="model"
    :rules="rules"
    label-placement="top"
    @submit.prevent="submit"
  >
    <AuthHeading :title="t('auth.registerTitle')" :subtitle="t('auth.registerSubtitle')" />
    <NAlert v-if="error" type="error" role="alert" class="form-alert">{{ error }}</NAlert>
    <NFormItem :label="t('auth.username')" path="username">
      <NInput v-model:value="model.username" autocomplete="username" />
    </NFormItem>
    <NFormItem :label="t('auth.email')" path="email">
      <NInput v-model:value="model.email" autocomplete="email" />
    </NFormItem>
    <NFormItem :label="t('auth.password')" path="password">
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
    <NButton type="primary" block attr-type="submit" :loading="auth.loading">
      {{ t('auth.register') }}
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
