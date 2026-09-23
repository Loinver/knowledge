<script setup lang="ts">
import type { FormInst, FormRules } from 'naive-ui'
import { NAlert, NButton, NForm, NFormItem, NInput } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { authApi } from '@/api/auth'
import { useApiError } from '@/composables/useApiError'
import { useAuthStore } from '@/stores/auth'
import AuthHeading from '@/views/auth/AuthHeading.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { toMessage } = useApiError()

const formRef = ref<FormInst | null>(null)
const model = ref({ account: '', password: '' })
const error = ref('')

/**
 * 公开注册默认关闭（账号由管理员发放）。拿不到配置时按关闭处理，
 * 否则会给用户一个必然失败的注册入口。
 */
const registrationEnabled = ref(false)

onMounted(async () => {
  try {
    registrationEnabled.value = (await authApi.config()).registration_enabled
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
  error.value = ''
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  try {
    await auth.login({ account: model.value.account, password: model.value.password })
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
    await router.replace(redirect || { name: 'dashboard' })
  } catch (err) {
    error.value = toMessage(err)
  }
}
</script>

<template>
  <NForm ref="formRef" :model="model" :rules="rules" label-placement="top" @submit.prevent="submit">
    <AuthHeading :title="t('auth.loginTitle')" :subtitle="t('auth.loginSubtitle')" />
    <NAlert v-if="error" type="error" role="alert" class="form-alert">{{ error }}</NAlert>
    <NFormItem :label="t('auth.account')" path="account">
      <NInput
        v-model:value="model.account"
        :placeholder="t('auth.accountPlaceholder')"
        autocomplete="username"
      />
    </NFormItem>
    <NFormItem :label="t('auth.password')" path="password">
      <NInput
        v-model:value="model.password"
        type="password"
        show-password-on="click"
        :placeholder="t('auth.passwordPlaceholder')"
        autocomplete="current-password"
        @keyup.enter="submit"
      />
    </NFormItem>
    <NButton type="primary" block attr-type="submit" :loading="auth.loading">
      {{ t('auth.login') }}
    </NButton>
    <div class="form-links">
      <RouterLink :to="{ name: 'forgot-password' }">{{ t('auth.forgot') }}</RouterLink>
      <RouterLink v-if="registrationEnabled" :to="{ name: 'register' }">
        {{ t('auth.toRegister') }}
      </RouterLink>
    </div>
  </NForm>
</template>

<style scoped>
.form-alert {
  margin-bottom: var(--space-3);
}
.form-links {
  display: flex;
  justify-content: space-between;
  margin-top: var(--space-3);
  font-size: var(--font-small);
}
.form-links a {
  text-decoration: none;
}
.form-links a:hover {
  text-decoration: underline;
}
</style>
