<script setup lang="ts">
import { FocusScope } from 'reka-ui'
import { nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import StarMark from '@/components/StarMark.vue'
import { useNavigation } from '@/layout/navigation/useNavigation'
import { useUiStore } from '@/stores/ui'

import NavigationBranch from './NavigationBranch.vue'

const { t } = useI18n()
const ui = useUiStore()
const { menuOptions, activeKey, expandedKeys, selectMenu, expandMenuPath } = useNavigation()
const navigation = ref<HTMLElement | null>(null)
function toggle(key: string) {
  expandedKeys.value = expandMenuPath(
    expandedKeys.value.includes(key)
      ? expandedKeys.value.filter((value) => value !== key)
      : [...expandedKeys.value, key],
  )
}
function close() {
  ui.closeMobileSider()
  document.getElementById('nav-toggle')?.focus()
}
watch(
  () => ui.collapsed,
  async (collapsed) => {
    if (!ui.narrow) return
    await nextTick()
    if (collapsed) document.getElementById('nav-toggle')?.focus()
    else navigation.value?.querySelector<HTMLElement>('button')?.focus()
  },
)
</script>
<template>
  <FocusScope
    :trapped="ui.narrow && !ui.collapsed"
    :loop="ui.narrow && !ui.collapsed"
    as-child
    @mount-auto-focus="$event.preventDefault()"
    @unmount-auto-focus="$event.preventDefault()"
  >
    <aside
      class="app-sider"
      :class="{ 'is-collapsed': ui.collapsed }"
      :inert="(ui.narrow && ui.collapsed) || undefined"
      @keydown.esc.stop="close"
    >
      <RouterLink
        class="brand"
        :to="{ name: 'dashboard' }"
        :aria-label="t('app.title')"
        :title="ui.collapsed ? t('app.title') : undefined"
      >
        <StarMark :size="22" /><span v-show="!ui.collapsed" class="brand-text"
          ><strong>{{ t('app.title') }}</strong
          ><small>{{ t('navigation.workspace') }}</small></span
        >
      </RouterLink>
      <nav ref="navigation" class="sider-scroll" :aria-label="t('ds.primaryNavigation')">
        <ul class="navigation">
          <NavigationBranch
            v-for="option in menuOptions"
            :key="String(option.key)"
            :node="option"
            :active="activeKey"
            :expanded="expandedKeys"
            :collapsed="ui.collapsed"
            @select="selectMenu"
            @toggle="toggle"
            @expand="ui.toggleSider()"
          />
        </ul>
      </nav>
      <div v-if="!ui.collapsed" class="sider-foot">{{ t('navigation.workspaceHint') }}</div>
    </aside>
  </FocusScope>
</template>
<style scoped>
.app-sider {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  height: 100%;
  color: var(--foreground-secondary);
  background: var(--surface-panel);
  border-right: 1px solid var(--border-muted);
}
.brand {
  display: flex;
  flex: none;
  gap: var(--space-2);
  align-items: center;
  height: var(--header-height);
  padding: 0 var(--space-4);
  overflow: hidden;
  color: var(--foreground-primary);
  text-decoration: none;
  white-space: nowrap;
  border-bottom: 1px solid var(--border-muted);
}
.brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.brand-text strong {
  font-size: var(--font-body);
  font-weight: 600;
}
.brand-text small {
  margin-top: 2px;
  color: var(--foreground-muted);
  font-size: 11px;
}
.sider-scroll {
  flex: 1;
  min-height: 0;
  padding: var(--space-2);
  overflow: auto;
}
.navigation {
  padding: 0;
  margin: 0;
  list-style: none;
}
.sider-foot {
  flex: none;
  padding: var(--space-4);
  font-size: var(--font-caption);
  color: var(--foreground-muted);
  border-top: 1px solid var(--border-muted);
}
@media (max-width: 1023px) {
  .app-sider {
    position: fixed;
    z-index: var(--z-navigation);
    inset: 0 auto 0 0;
    width: var(--sider-width);
    max-width: calc(100vw - 32px);
    height: 100dvh;
    box-shadow: var(--shadow-overlay);
    transform: translateX(0);
    transition: transform var(--duration-normal) var(--ease-out);
  }
  .app-sider.is-collapsed {
    transform: translateX(-100%);
  }
}
</style>
