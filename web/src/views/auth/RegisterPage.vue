<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { authApi } from '@/api/auth'
import { getSessionGeneration } from '@/api/tokens'
import type { FormInst, FormRules } from '@/components/ui'
import { FormContainer, FormField, UiAlert, UiButton, UiInput } from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useAuthStore } from '@/stores/auth'
import AuthHeading from '@/views/auth/components/AuthHeading.vue'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const { toMessage } = useApiError()

const formRef = ref<FormInst | null>(null)
const model = ref({ username: '', email: '', password: '', confirm: '' })
const error = ref('')
const submitting = ref(false)
let alive = true
let configGeneration = 0
onBeforeUnmount(() => {
  alive = false
  configGeneration++
})

/**
 * 公开注册默认关闭：账号由管理员在「系统管理 → 用户管理」里发放。
 * `null` 表示配置还没回来，此时不渲染表单，避免闪一下再被拒绝。
 */
const registrationEnabled = ref<boolean | null>(null)
const passwordMin = ref(8)
const configError = ref('')

async function loadConfig() {
  const generation = ++configGeneration
  registrationEnabled.value = null
  configError.value = ''
  try {
    const config = await authApi.config()
    if (!alive || generation !== configGeneration) return
    registrationEnabled.value = config.registration_enabled
    passwordMin.value = config.password_min_length
  } catch (cause) {
    if (!alive || generation !== configGeneration) return
    registrationEnabled.value = false
    configError.value = toMessage(cause)
  }
}
onMounted(loadConfig)

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
      validator: (_rule, value) => value === model.value.password,
      message: t('auth.rules.passwordMismatch'),
      trigger: ['blur', 'input'],
    },
  ],
}))

async function submit() {
  if (!alive || !formRef.value || auth.loading || submitting.value || !registrationEnabled.value)
    return
  const path = route.fullPath
  error.value = ''
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  if (
    !alive ||
    route.fullPath !== path ||
    auth.loading ||
    submitting.value ||
    !registrationEnabled.value
  )
    return
  submitting.value = true
  let generation = getSessionGeneration()
  try {
    const request = auth.register({
      username: model.value.username,
      email: model.value.email,
      password: model.value.password,
    })
    generation = getSessionGeneration()
    await request
    if (
      !alive ||
      route.fullPath !== path ||
      generation !== getSessionGeneration() ||
      !auth.isAuthenticated
    )
      return
    await router.replace({ name: 'dashboard' })
  } catch (err) {
    if (alive && route.fullPath === path && generation === getSessionGeneration())
      error.value = toMessage(err)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div v-if="registrationEnabled === false" class="closed auth-flow">
    <AuthHeading :title="t('auth.registerTitle')" />
    <UiAlert v-if="configError" type="error" class="form-alert"
      >{{ configError }} <UiButton @click="loadConfig">{{ t('ui.retry') }}</UiButton></UiAlert
    >
    <UiAlert v-else type="warning" role="alert" class="form-alert">
      {{ t('auth.registrationClosed') }}
    </UiAlert>
    <div class="form-links">
      <RouterLink :to="{ name: 'login' }">{{ t('auth.toLogin') }}</RouterLink>
    </div>
  </div>

  <FormContainer
    v-else-if="registrationEnabled"
    ref="formRef"
    class="auth-flow"
    :model="model"
    :rules="rules"
    :submitting="submitting || auth.loading"
    label-placement="top"
    @submit="submit"
  >
    <AuthHeading :title="t('auth.registerTitle')" :subtitle="t('auth.registerSubtitle')" />
    <UiAlert v-if="error" type="error" role="alert" class="form-alert">{{ error }}</UiAlert>
    <FormField :label="t('auth.username')" path="username">
      <UiInput
        v-model:value="model.username"
        :input-props="{ 'aria-label': t('auth.username') }"
        autocomplete="username"
      />
    </FormField>
    <FormField :label="t('auth.email')" path="email">
      <UiInput
        v-model:value="model.email"
        :input-props="{ 'aria-label': t('auth.email') }"
        autocomplete="email"
      />
    </FormField>
    <FormField :label="t('auth.password')" path="password">
      <UiInput
        v-model:value="model.password"
        :input-props="{ 'aria-label': t('auth.password') }"
        type="password"
        show-password-on="click"
        autocomplete="new-password"
      />
    </FormField>
    <FormField :label="t('auth.confirmPassword')" path="confirm">
      <UiInput
        v-model:value="model.confirm"
        :input-props="{ 'aria-label': t('auth.confirmPassword') }"
        type="password"
        show-password-on="click"
        autocomplete="new-password"
      />
    </FormField>
    <UiButton type="primary" block attr-type="submit" :loading="auth.loading">
      {{ t('auth.register') }}
    </UiButton>
    <div class="form-links">
      <RouterLink :to="{ name: 'login' }">{{ t('auth.toLogin') }}</RouterLink>
    </div>
  </FormContainer>
  <div v-else class="auth-flow">
    <AuthHeading :title="t('auth.registerTitle')" />
    <p role="status">{{ t('common.loading') }}</p>
  </div>
</template>

<style scoped src="./AuthForm.css"></style>
