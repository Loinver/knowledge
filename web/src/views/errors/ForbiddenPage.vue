<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { UiButton } from '@/components/ui'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const statusCode = 403
const refreshing = ref(false)
async function refreshPermissions() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    await auth.loadMe()
    const target = route.query.redirect
    if (
      auth.isAdmin &&
      typeof target === 'string' &&
      target.startsWith('/') &&
      !target.startsWith('//')
    ) {
      await router.replace(target)
    }
  } finally {
    refreshing.value = false
  }
}
</script>

<template>
  <main class="error-workspace">
    <section class="error-panel">
      <div class="error-code">
        <strong>{{ statusCode }}</strong
        ><span>{{ t('operationsUi.error403') }}</span>
      </div>
      <div class="error-content">
        <span class="eyebrow">{{ t('operationsUi.recovery') }}</span>
        <h1>{{ t('page.forbiddenTitle') }}</h1>
        <p>{{ t('page.forbiddenHint') }}</p>
        <dl class="error-identity">
          <div>
            <dt>{{ t('auth.username') }}</dt>
            <dd>{{ auth.user?.username ?? t('account.anonymous') }}</dd>
          </div>
          <div>
            <dt>{{ t('account.role') }}</dt>
            <dd>{{ auth.user ? t(`account.roles.${auth.user.role}`) : t('common.noneValue') }}</dd>
          </div>
        </dl>
        <div class="error-actions">
          <UiButton :loading="refreshing" @click="refreshPermissions">{{
            t('appUi.refreshPermissions')
          }}</UiButton>
          <UiButton type="primary" @click="router.push({ name: 'dashboard' })">{{
            t('page.backToDashboard')
          }}</UiButton>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped src="./ErrorWorkspace.css"></style>
