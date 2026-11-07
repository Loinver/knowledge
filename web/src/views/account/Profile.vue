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
  NTag,
  useMessage,
} from 'naive-ui'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { authApi } from '@/api/auth'
import { getSessionGeneration } from '@/api/tokens'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const auth = useAuthStore()
const message = useMessage()
const { toMessage } = useApiError()

const formRef = ref<FormInst | null>(null)
const model = ref({ display_name: '', avatar_url: '' })
const error = ref('')
const saving = ref(false)
let formGeneration: string | null = null
watch(
  () => auth.user?.id,
  () => {
    formGeneration = auth.user ? getSessionGeneration() : null
    model.value = {
      display_name: auth.user?.display_name ?? '',
      avatar_url: auth.user?.avatar_url ?? '',
    }
    error.value = ''
  },
  { immediate: true, flush: 'sync' },
)

const rules = computed<FormRules>(() => ({
  display_name: {
    max: 32,
    message: t('account.rules.displayNameMax'),
    trigger: ['blur', 'input'],
  },
  avatar_url: { type: 'url', message: t('account.rules.avatarUrl'), trigger: ['blur', 'input'] },
}))

const lastLogin = computed(() => {
  const raw = auth.user?.last_login_at
  if (!raw) return t('account.never')
  return new Date(raw).toLocaleString()
})

onMounted(() => {
  void auth.loadMe()
})

async function submit() {
  const generation = formGeneration
  if (!generation || generation !== getSessionGeneration() || saving.value || !auth.user) return
  const payload = {
    display_name: model.value.display_name.trim() || null,
    avatar_url: model.value.avatar_url.trim() || null,
  }
  error.value = ''
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  if (generation !== getSessionGeneration()) return
  saving.value = true
  try {
    // 传 null 才是「清空」：后端按 exclude_unset 处理，省略字段表示不改。
    const updated = await authApi.updateProfile(payload, generation)
    if (auth.setUser(updated, generation)) message.success(t('account.saved'))
  } catch (err) {
    if (generation === getSessionGeneration()) error.value = toMessage(err)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section>
    <PageHeader :title="t('account.profile')" :description="t('account.profileHint')" />
    <NAlert v-if="error" type="error" role="alert" class="alert">{{ error }}</NAlert>

    <NCard size="small" class="card">
      <NDescriptions :column="2" bordered label-placement="left">
        <NDescriptionsItem :label="t('auth.username')">{{ auth.user?.username }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('auth.email')">{{ auth.user?.email }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('account.role')">
          <NTag size="small">{{ t(`account.roles.${auth.user?.role ?? 'VIEWER'}`) }}</NTag>
        </NDescriptionsItem>
        <NDescriptionsItem :label="t('account.status')">
          <NTag size="small" :type="auth.user?.status === 'ACTIVE' ? 'success' : 'warning'">
            {{ t(`account.statuses.${auth.user?.status ?? 'ACTIVE'}`) }}
          </NTag>
        </NDescriptionsItem>
        <NDescriptionsItem :label="t('account.lastLogin')" :span="2">
          {{ lastLogin }}
        </NDescriptionsItem>
      </NDescriptions>
    </NCard>

    <NCard size="small" class="card" :title="t('account.editProfile')">
      <NForm ref="formRef" :model="model" :rules="rules" label-placement="top">
        <NFormItem :label="t('account.displayName')" path="display_name">
          <NInput v-model:value="model.display_name" :placeholder="auth.user?.username" />
        </NFormItem>
        <NFormItem :label="t('account.avatarUrl')" path="avatar_url">
          <NInput v-model:value="model.avatar_url" placeholder="https://" />
        </NFormItem>
        <NButton type="primary" :disabled="!auth.user" :loading="saving" @click="submit">{{
          t('common.save')
        }}</NButton>
      </NForm>
    </NCard>
  </section>
</template>

<style scoped>
.alert,
.card {
  margin-bottom: var(--space-4);
}
</style>
