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
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { toMessage } = useApiError()

const formRef = ref<FormInst | null>(null)
const model = ref({ account: '', password: '' })
const error = ref('')
const submitting = ref(false)
let alive = true
onBeforeUnmount(() => {
  alive = false
})

/**
 * 公开注册默认关闭（账号由管理员发放）。拿不到配置时按关闭处理，
 * 否则会给用户一个必然失败的注册入口。
 */
const registrationEnabled = ref(false)

onMounted(async () => {
  try {
    const config = await authApi.config()
    if (alive) registrationEnabled.value = config.registration_enabled
  } catch {
    registrationEnabled.value = false
  }
})

const rules = computed<FormRules>(() => ({
  account: { required: true, message: t('auth.rules.accountRequired'), trigger: ['blur', 'input'] },
  password: {
    required: true,
    message: t('auth.rules.passwordRequired'),
    trigger: ['blur', 'input'],
  },
}))

async function submit() {
  if (!alive || !formRef.value || auth.loading || submitting.value) return
  const path = route.fullPath
  error.value = ''
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  if (!alive || route.fullPath !== path || auth.loading || submitting.value) return
  submitting.value = true
  let generation = getSessionGeneration()
  try {
    const request = auth.login({ account: model.value.account, password: model.value.password })
    generation = getSessionGeneration()
    await request
    if (
      !alive ||
      route.fullPath !== path ||
      generation !== getSessionGeneration() ||
      !auth.isAuthenticated
    )
      return
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
    await router.replace(redirect || { name: 'dashboard' })
  } catch (err) {
    if (alive && route.fullPath === path && generation === getSessionGeneration())
      error.value = toMessage(err)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <FormContainer
    ref="formRef"
    class="auth-flow"
    :model="model"
    :rules="rules"
    :submitting="submitting || auth.loading"
    label-placement="top"
    @submit="submit"
  >
    <AuthHeading :title="t('auth.loginTitle')" :subtitle="t('auth.loginSubtitle')" />
    <UiAlert v-if="error" type="error" role="alert" class="form-alert">{{ error }}</UiAlert>
    <FormField :label="t('auth.account')" path="account">
      <UiInput
        v-model:value="model.account"
        :placeholder="t('auth.accountPlaceholder')"
        autocomplete="username"
      />
    </FormField>
    <FormField :label="t('auth.password')" path="password">
      <UiInput
        v-model:value="model.password"
        type="password"
        show-password-on="click"
        :placeholder="t('auth.passwordPlaceholder')"
        autocomplete="current-password"
      />
    </FormField>
    <UiButton type="primary" block attr-type="submit" :loading="auth.loading">
      {{ t('auth.login') }}
    </UiButton>
    <div class="form-links">
      <RouterLink :to="{ name: 'forgot-password' }">{{ t('auth.forgot') }}</RouterLink>
      <RouterLink v-if="registrationEnabled" :to="{ name: 'register' }">
        {{ t('auth.toRegister') }}
      </RouterLink>
    </div>
  </FormContainer>
</template>

<style scoped src="./AuthForm.css"></style>
