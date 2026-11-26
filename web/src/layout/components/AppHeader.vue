<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'
import QuickSearch from '@/layout/components/QuickSearch.vue'
import UserDropdown from '@/layout/components/UserDropdown.vue'
import { useNavigation } from '@/layout/navigation/useNavigation'
import { useLocaleStore } from '@/stores/locale'
import { useUiStore } from '@/stores/ui'

const { t } = useI18n()
const ui = useUiStore()
const localeStore = useLocaleStore()
const { breadcrumb } = useNavigation()
const route = useRoute()
</script>
<template>
  <header class="app-header">
    <div class="left">
      <UiButton
        id="nav-toggle"
        quaternary
        :aria-label="ui.collapsed ? t('layout.expandSider') : t('layout.collapseSider')"
        @click="ui.toggleSider()"
        ><AppIcon name="menu"
      /></UiButton>
      <RouterLink class="product-name" :to="{ name: 'dashboard' }">{{ t('app.title') }}</RouterLink>
      <nav class="breadcrumbs" :aria-label="t('ds.breadcrumb')">
        <ol>
          <li v-for="(crumb, index) in breadcrumb" :key="crumb.key">
            <span v-if="index" class="crumb-separator" aria-hidden="true">{{ '/' }}</span>
            <RouterLink
              v-if="crumb.to && index < breadcrumb.length - 1"
              :to="{
                name: crumb.to,
                params: crumb.to === 'knowledge-base-detail' ? route.params : {},
                query: route.query,
              }"
              :title="crumb.label"
              class="crumb-link"
              >{{ crumb.label }}</RouterLink
            >
            <span
              v-else
              class="crumb-current"
              :title="crumb.label"
              :aria-current="index === breadcrumb.length - 1 ? 'page' : undefined"
              >{{ crumb.label }}</span
            >
          </li>
        </ol>
      </nav>
    </div>
    <div class="right">
      <QuickSearch />
      <UiButton
        quaternary
        :aria-label="t('layout.switchLocale')"
        @click="localeStore.change(localeStore.current === 'zh-CN' ? 'en-US' : 'zh-CN')"
        ><AppIcon name="globe" /><span class="btn-text">{{ localeStore.label }}</span></UiButton
      >
      <UiButton
        quaternary
        :aria-label="ui.isDark ? t('layout.toLight') : t('layout.toDark')"
        @click="ui.toggleTheme()"
        ><AppIcon :name="ui.isDark ? 'sun' : 'moon'"
      /></UiButton>
      <UserDropdown />
    </div>
  </header>
</template>
<style scoped>
.app-header {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  height: var(--header-height);
  padding: 0 var(--space-4);
  background: var(--surface-panel);
  border-bottom: 1px solid var(--border-muted);
}
.left,
.right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}
.product-name {
  flex: none;
  font-size: 13px;
  font-weight: 650;
  color: var(--foreground-primary);
  text-decoration: none;
  padding-right: 16px;
  margin-right: 6px;
  border-right: 1px solid var(--border-muted);
}
.left {
  flex: 1;
  overflow: hidden;
}
.right {
  flex: none;
}
.breadcrumbs {
  min-width: 0;
  overflow: hidden;
}
.breadcrumbs ol {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0;
  margin: 0;
  list-style: none;
}
.breadcrumbs li {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  min-width: 0;
  font-size: var(--font-small);
}
.crumb-link,
.crumb-current {
  max-width: min(32vw, 280px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.crumb-link,
.crumb-separator {
  color: var(--foreground-muted);
  text-decoration: none;
}
.crumb-current {
  color: var(--foreground-secondary);
}
.crumb-link:hover {
  color: var(--action-primary);
}
.btn-text {
  font-size: var(--font-caption);
}
@media (max-width: 767px) {
  .app-header {
    padding: 0 var(--space-2);
    gap: var(--space-1);
  }
  .right,
  .left {
    gap: 2px;
  }
  .product-name,
  .btn-text {
    display: none;
  }
  .breadcrumbs li:not(:last-child) {
    display: none;
  }
  .crumb-separator {
    display: none;
  }
  .crumb-current {
    max-width: 30vw;
  }
}
</style>
