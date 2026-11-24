<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteLeave } from 'vue-router'

import { authApi } from '@/api/auth'
import { getSessionGeneration } from '@/api/tokens'
import PageHeader from '@/components/PageHeader.vue'
import type { FormInst, FormRules } from '@/components/ui'
import {
  FormContainer,
  FormField,
  UiAlert,
  UiButton,
  UiInput,
  UiTag,
  useMessage,
} from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useOwnedMutation } from '@/composables/useOwnedMutation'
import { useAuthStore } from '@/stores/auth'

const { t, locale } = useI18n()
const auth = useAuthStore()
const message = useMessage()
const { toMessage } = useApiError()

const formRef = ref<FormInst | null>(null)
const model = ref({ display_name: '', avatar_url: '' })
const mutation = useOwnedMutation(() => auth.user?.id, toMessage)
const { error, busy: saving } = mutation
let alive = true
let formVersion = 0
onBeforeUnmount(() => {
  alive = false
  formVersion++
})
onBeforeRouteLeave(() => {
  const user = auth.user
  if (
    !user ||
    (model.value.display_name.trim() === (user.display_name ?? '') &&
      model.value.avatar_url.trim() === (user.avatar_url ?? ''))
  )
    return true
  return typeof window === 'undefined' || window.confirm(t('ui.unsaved'))
})
function cancel() {
  if (saving.value) return
  formVersion++
  model.value = {
    display_name: auth.user?.display_name ?? '',
    avatar_url: auth.user?.avatar_url ?? '',
  }
  mutation.invalidate()
  formRef.value?.restoreValidation()
}
let formGeneration: string | null = null
watch(
  () => auth.user?.id,
  () => {
    formVersion++
    formGeneration = auth.user ? getSessionGeneration() : null
    model.value = {
      display_name: auth.user?.display_name ?? '',
      avatar_url: auth.user?.avatar_url ?? '',
    }
    mutation.invalidate()
    formRef.value?.restoreValidation()
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
  return new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(raw),
  )
})

onMounted(() => {
  void auth.loadMe()
})

async function submit() {
  const generation = formGeneration
  const version = formVersion
  const draft = model.value
  if (
    !alive ||
    !formRef.value ||
    !generation ||
    generation !== getSessionGeneration() ||
    saving.value ||
    !auth.user
  )
    return
  const payload = {
    display_name: model.value.display_name.trim() || null,
    avatar_url: model.value.avatar_url.trim() || null,
  }
  mutation.invalidate()
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  if (
    !alive ||
    version !== formVersion ||
    draft !== model.value ||
    generation !== getSessionGeneration() ||
    saving.value
  )
    return
  // 传 null 才是「清空」：后端按 exclude_unset 处理，省略字段表示不改。
  const updated = await mutation.run(() => authApi.updateProfile(payload, generation))
  if (!updated || !alive || version !== formVersion || generation !== getSessionGeneration()) return
  if (auth.setUser(updated, generation)) {
    model.value = { display_name: updated.display_name ?? '', avatar_url: updated.avatar_url ?? '' }
    message.success(t('account.saved'))
  }
}
</script>

<template>
  <section class="account-page">
    <PageHeader :title="t('account.profile')" :description="t('account.profileHint')" />
    <UiAlert v-if="error" type="error" role="alert" class="alert">{{ error }}</UiAlert>

    <div class="account-workspace">
      <aside class="identity-panel">
        <header class="group-heading">
          <span>{{ t('operationsUi.identity') }}</span>
          <h2>{{ auth.user?.display_name || auth.user?.username || t('common.noneValue') }}</h2>
        </header>
        <dl class="identity-list">
          <div>
            <dt>{{ t('auth.username') }}</dt>
            <dd class="mono">{{ auth.user?.username ?? t('common.noneValue') }}</dd>
          </div>
          <div>
            <dt>{{ t('auth.email') }}</dt>
            <dd>{{ auth.user?.email ?? t('common.noneValue') }}</dd>
          </div>
          <div>
            <dt>{{ t('account.role') }}</dt>
            <dd>
              <UiTag size="small">{{ t(`account.roles.${auth.user?.role ?? 'VIEWER'}`) }}</UiTag>
            </dd>
          </div>
          <div>
            <dt>{{ t('account.status') }}</dt>
            <dd>
              <UiTag
                v-if="auth.user"
                size="small"
                :type="auth.user.status === 'ACTIVE' ? 'success' : 'warning'"
                >{{ t(`account.statuses.${auth.user.status}`) }}</UiTag
              ><span v-else>{{ t('common.noneValue') }}</span>
            </dd>
          </div>
          <div>
            <dt>{{ t('account.lastLogin') }}</dt>
            <dd>{{ lastLogin }}</dd>
          </div>
        </dl>
      </aside>

      <section class="settings-panel">
        <header class="group-heading">
          <h2>{{ t('account.editProfile') }}</h2>
          <p>{{ t('account.profileHint') }}</p>
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
          <FormField :label="t('account.displayName')" path="display_name">
            <UiInput v-model:value="model.display_name" :placeholder="auth.user?.username" />
          </FormField>
          <FormField :label="t('account.avatarUrl')" path="avatar_url">
            <UiInput v-model:value="model.avatar_url" placeholder="https://" />
          </FormField>
          <div class="form-actions">
            <UiButton type="primary" attr-type="submit" :disabled="!auth.user" :loading="saving">{{
              t('common.save')
            }}</UiButton>
            <UiButton class="cancel" :disabled="saving" @click="cancel">{{
              t('common.cancel')
            }}</UiButton>
          </div>
        </FormContainer>
      </section>
    </div>
  </section>
</template>

<style scoped src="./AccountSettings.css"></style>
