<script setup lang="ts">
import { NBreadcrumb, NBreadcrumbItem, NButton, NLayoutHeader } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import UserDropdown from '@/layout/components/UserDropdown.vue'
import { useNavigation } from '@/layout/useNavigation'
import { useLocaleStore } from '@/stores/locale'
import { useUiStore } from '@/stores/ui'

const { t } = useI18n()
const ui = useUiStore()
const localeStore = useLocaleStore()
const { breadcrumb } = useNavigation()
</script>

<template>
  <NLayoutHeader bordered class="app-header">
    <div class="left">
      <NButton
        quaternary
        :aria-label="ui.collapsed ? t('layout.expandSider') : t('layout.collapseSider')"
        @click="ui.toggleSider()"
      >
        <AppIcon name="menu" />
      </NButton>
      <NBreadcrumb>
        <NBreadcrumbItem v-for="(crumb, index) in breadcrumb" :key="crumb.key">
          <RouterLink
            v-if="crumb.to && index < breadcrumb.length - 1"
            :to="{ name: crumb.to }"
            class="crumb-link"
            >{{ crumb.label }}</RouterLink
          >
          <span v-else>{{ crumb.label }}</span>
        </NBreadcrumbItem>
      </NBreadcrumb>
    </div>
    <div class="right">
      <NButton
        quaternary
        :aria-label="t('layout.switchLocale')"
        @click="localeStore.change(localeStore.current === 'zh-CN' ? 'en-US' : 'zh-CN')"
      >
        <AppIcon name="globe" />
        <span class="btn-text">{{ localeStore.label }}</span>
      </NButton>
      <NButton
        quaternary
        :aria-label="ui.isDark ? t('layout.toLight') : t('layout.toDark')"
        @click="ui.toggleTheme()"
      >
        <AppIcon :name="ui.isDark ? 'sun' : 'moon'" />
      </NButton>
      <UserDropdown />
    </div>
  </NLayoutHeader>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--header-height);
  padding: 0 var(--space-4);
}
.left,
.right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.crumb-link {
  color: var(--text-secondary);
  text-decoration: none;
}
.crumb-link:hover {
  color: var(--pri);
}
.btn-text {
  margin-left: var(--space-1);
  font-size: var(--font-small);
}
</style>
