<script setup lang="ts">
import { NButton, NResult } from 'naive-ui'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
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
  <div class="forbidden">
    <NResult status="403" :title="t('page.forbiddenTitle')" :description="t('page.forbiddenHint')">
      <template #footer>
        <NButton :loading="refreshing" @click="refreshPermissions">{{
          t('appUi.refreshPermissions')
        }}</NButton>
        <NButton type="primary" @click="router.push({ name: 'dashboard' })">
          {{ t('page.backToDashboard') }}
        </NButton>
      </template>
    </NResult>
  </div>
</template>

<style scoped>
.forbidden {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}
.forbidden :deep(.n-button) {
  margin: 4px;
}
</style>
