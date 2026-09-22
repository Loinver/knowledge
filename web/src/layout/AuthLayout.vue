<script setup lang="ts">
import { NButton, NCard } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { RouterView } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import { useLocaleStore } from '@/stores/locale'
import { useUiStore } from '@/stores/ui'

const { t } = useI18n()
const ui = useUiStore()
const localeStore = useLocaleStore()
</script>

<template>
  <div class="auth-layout">
    <div class="auth-toolbar">
      <NButton
        quaternary
        size="small"
        :aria-label="t('layout.switchLocale')"
        @click="localeStore.change(localeStore.current === 'zh-CN' ? 'en-US' : 'zh-CN')"
        >{{ localeStore.label }}</NButton
      >
      <NButton
        quaternary
        size="small"
        circle
        :aria-label="ui.isDark ? t('layout.toLight') : t('layout.toDark')"
        @click="ui.toggleTheme()"
      >
        <AppIcon :name="ui.isDark ? 'sun' : 'moon'" :size="16" />
      </NButton>
    </div>
    <div class="auth-main">
      <NCard class="auth-card" :bordered="false">
        <div class="auth-brand">
          <span class="brand-mark">{{ t('app.shortName') }}</span>
          <div>
            <h1>{{ t('app.title') }}</h1>
            <p>{{ t('app.subtitle') }}</p>
          </div>
        </div>
        <RouterView />
      </NCard>
    </div>
    <footer class="auth-footer">{{ t('layout.authFooter') }}</footer>
  </div>
</template>

<style scoped>
.auth-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--bg-subtle);
}
.auth-toolbar {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  padding: var(--space-4);
}
.auth-main {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  padding: var(--space-4) var(--space-4) var(--space-6);
}
.auth-card {
  width: 100%;
  max-width: 400px;
  box-shadow: var(--shadow-md);
}
.auth-brand {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  margin-bottom: var(--space-5);
}
.brand-mark {
  display: inline-flex;
  flex: 0 0 36px;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  color: #fff;
  font-size: var(--font-caption);
  font-weight: 700;
  background: var(--pri);
  border-radius: var(--radius-medium);
}
.auth-brand h1 {
  margin: 0;
  font-size: 18px;
}
.auth-brand p {
  margin: 2px 0 0;
  color: var(--text-tertiary);
  font-size: var(--font-caption);
}
.auth-footer {
  padding: var(--space-4);
  color: var(--text-tertiary);
  font-size: var(--font-caption);
  text-align: center;
}
</style>
