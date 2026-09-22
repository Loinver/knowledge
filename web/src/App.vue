<script setup lang="ts">
import {
  enUS,
  NConfigProvider,
  NDialogProvider,
  NLoadingBarProvider,
  NMessageProvider,
  NNotificationProvider,
  zhCN,
} from 'naive-ui'
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterView } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { darkTheme, darkThemeOverrides, lightThemeOverrides } from '@/theme/naive'

const { locale } = useI18n()
const ui = useUiStore()
const auth = useAuthStore()

const theme = computed(() => (ui.isDark ? darkTheme : null))
const themeOverrides = computed(() => (ui.isDark ? darkThemeOverrides : lightThemeOverrides))

onMounted(() => {
  // 刷新后恢复登录态与用户信息；受限页需要角色时守卫会再补拉一次
  void auth.loadMe()
})
</script>

<template>
  <NConfigProvider
    :theme="theme"
    :theme-overrides="themeOverrides"
    :locale="locale === 'zh-CN' ? zhCN : enUS"
  >
    <!-- 全局反馈容器。此前 App 未挂载 provider，而多个页面调用 useMessage()，
         naive-ui 在无 provider 时会直接抛错，那些页面运行时不工作。 -->
    <NMessageProvider>
      <NDialogProvider>
        <NNotificationProvider>
          <NLoadingBarProvider>
            <RouterView />
          </NLoadingBarProvider>
        </NNotificationProvider>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>
