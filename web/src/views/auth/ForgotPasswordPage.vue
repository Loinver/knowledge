<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
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
const router = useRouter()
const route = useRoute()
const { toMessage } = useApiError()

const formRef = ref<FormInst | null>(null)
const model = ref({ email: '' })
const error = ref('')
const sent = ref(false)
const mutation = useOwnedMutation(() => [route.fullPath, getSessionGeneration()], toMessage)
const { busy: loading } = mutation
let alive = true
let configGeneration = 0
onBeforeUnmount(() => {
  alive = false
  configGeneration++
})

/**
 * 平台还没有邮件服务，自助找回只在开发态下发令牌时可用。
 * 拿不到配置时按关闭处理：宁可让用户去找管理员，也不给一个必然失败的表单。
 */
const resetEnabled = ref(false)
const configLoaded = ref(false)
const configError = ref('')

async function loadConfig() {
  const generation = ++configGeneration
  configLoaded.value = false
  configError.value = ''
  try {
    const config = await authApi.config()
    if (alive && generation === configGeneration) resetEnabled.value = config.password_reset_enabled
  } catch (cause) {
    if (!alive || generation !== configGeneration) return
    resetEnabled.value = false
    configError.value = toMessage(cause)
  } finally {
    if (alive && generation === configGeneration) configLoaded.value = true
  }
}
onMounted(loadConfig)

const rules = computed<FormRules>(() => ({
  email: [
    { required: true, message: t('auth.rules.emailRequired'), trigger: ['blur', 'input'] },
    { type: 'email', message: t('auth.rules.emailPattern'), trigger: ['blur', 'input'] },
  ],
}))

async function submit() {
  if (!alive || !formRef.value || !resetEnabled.value || loading.value || sent.value) return
  const generation = getSessionGeneration()
  const path = route.fullPath
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
    !resetEnabled.value ||
    loading.value ||
    sent.value
  )
    return
  const result = await mutation.run(() => authApi.forgotPassword(model.value.email))
  if (!alive || path !== route.fullPath || generation !== getSessionGeneration()) return
  if (!result) {
    error.value = mutation.error.value
    return
  }
  // 开发态后端把重置令牌放在响应里：拿到令牌就直接进重置页，省掉手工拷贝那一步。
  if (result.reset_token) {
    await router.replace({
      name: 'reset-password',
      query: { token: result.reset_token },
    })
    return
  }
  sent.value = true
}
</script>

<template>
  <FormContainer
    ref="formRef"
    class="auth-flow"
    :model="model"
    :rules="rules"
    :submitting="loading"
    :disabled="sent"
    label-placement="top"
    @submit="submit"
  >
    <AuthHeading
      :title="t('auth.forgotTitle')"
      :subtitle="resetEnabled ? t('auth.forgotHint') : undefined"
    />
    <p v-if="!configLoaded" role="status">{{ t('common.loading') }}</p>
    <UiAlert v-else-if="configError" type="error" class="form-alert"
      >{{ configError }} <UiButton @click="loadConfig">{{ t('ui.retry') }}</UiButton></UiAlert
    >
    <UiAlert v-else-if="!resetEnabled" type="info" role="status" class="form-alert">
      {{ t('auth.resetUnavailable') }}
    </UiAlert>
    <template v-else-if="configLoaded">
      <UiAlert v-if="error" type="error" role="alert" class="form-alert">{{ error }}</UiAlert>
      <UiAlert v-if="sent" type="success" role="status" class="form-alert">
        {{ t('auth.forgotSent') }}
      </UiAlert>
      <FormField :label="t('auth.email')" path="email">
        <UiInput v-model:value="model.email" autocomplete="email" />
      </FormField>
      <UiButton type="primary" block attr-type="submit" :loading="loading" :disabled="sent">
        {{ t('auth.sendResetLink') }}
      </UiButton>
    </template>
    <div class="form-links">
      <RouterLink :to="{ name: 'login' }">{{ t('auth.toLogin') }}</RouterLink>
    </div>
  </FormContainer>
</template>

<style scoped src="./AuthForm.css"></style>
