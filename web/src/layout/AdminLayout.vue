<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterView, useRoute } from 'vue-router'

import AppHeader from '@/layout/components/AppHeader.vue'
import AppSider from '@/layout/components/AppSider.vue'
import ModuleNavigation from '@/layout/components/ModuleNavigation.vue'
import { providePageIdentity } from '@/layout/navigation/usePageIdentity'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const { t } = useI18n()
const route = useRoute()
providePageIdentity()
const fullBleed = computed(() => route.meta.fullBleed === true)
</script>
<template>
  <a class="skip-link" href="#main-content">{{ t('ds.skipToContent') }}</a>
  <div class="admin-layout" :class="{ 'is-collapsed': ui.collapsed }">
    <AppSider />
    <button
      v-if="ui.narrow && !ui.collapsed"
      class="mobile-backdrop"
      type="button"
      :aria-label="t('layout.collapseSider')"
      @click="ui.closeMobileSider()"
    />
    <div class="admin-main">
      <AppHeader />
      <ModuleNavigation />
      <main id="main-content" tabindex="-1" :class="['content', { 'content--bleed': fullBleed }]">
        <RouterView />
      </main>
    </div>
  </div>
</template>
<style scoped>
.admin-layout {
  display: grid;
  grid-template-columns: var(--sider-width) minmax(0, 1fr);
  height: 100dvh;
  overflow: hidden;
}
.admin-layout.is-collapsed {
  grid-template-columns: var(--sider-collapsed-width) minmax(0, 1fr);
}
.admin-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
.content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  padding: var(--page-gutter);
  overflow: auto;
  overscroll-behavior: contain;
  background: var(--surface-panel);
}
.content--bleed {
  padding: 0;
  overflow: hidden;
}
.mobile-backdrop {
  position: fixed;
  z-index: var(--z-nav-backdrop);
  inset: 0;
  width: 100%;
  height: 100%;
  padding: 0;
  background: var(--overlay-scrim);
  border: 0;
}
.skip-link {
  position: fixed;
  z-index: var(--z-toast);
  top: var(--space-2);
  left: var(--space-2);
  padding: var(--space-2) var(--space-3);
  color: var(--action-foreground);
  background: var(--action-primary);
  border-radius: var(--radius-control);
  transform: translateY(-160%);
}
.skip-link:focus {
  transform: translateY(0);
}
@media (max-width: 1023px) {
  .admin-layout,
  .admin-layout.is-collapsed {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
