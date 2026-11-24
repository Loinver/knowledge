<script setup lang="ts">
import { onMounted, watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterView, useRoute } from 'vue-router'

import UiFeedbackProvider from '@/components/ui/UiFeedbackProvider.vue'
import { identityFor } from '@/layout/navigation/routeIdentity'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

const { t } = useI18n()
const route = useRoute()
useUiStore()
const auth = useAuthStore()

watchEffect(() => {
  const title = identityFor(route.name)?.title
  if (typeof document !== 'undefined')
    document.title = title ? `${t(title)} · ${t('app.title')}` : t('app.title')
})

onMounted(() => {
  // 刷新后恢复登录态与用户信息；受限页需要角色时守卫会再补拉一次
  void auth.loadMe()
})
</script>

<template>
  <UiFeedbackProvider><RouterView /></UiFeedbackProvider>
</template>
