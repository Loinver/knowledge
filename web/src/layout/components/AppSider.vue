<script setup lang="ts">
import { FocusScope } from 'reka-ui'
import { nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import StarMark from '@/components/StarMark.vue'
import { menuLeaves, type MenuNode, menuTrail } from '@/layout/navigation/menuConfig'
import { useNavigation } from '@/layout/navigation/useNavigation'
import { useUiStore } from '@/stores/ui'

import NavigationBranch from './NavigationBranch.vue'

const { t } = useI18n()
const ui = useUiStore()
const { tree, menuOptions, activeKey, expandedKeys, selectMenu, expandMenuPath } = useNavigation()
function openModule(node: MenuNode) {
  const destination = menuLeaves([node])[0]
  if (destination) selectMenu(node.defaultRoute ?? destination.key)
}
function moduleActive(node: MenuNode) {
  return menuTrail(activeKey.value, [node]).length > 0
}
const railLabels: Record<string, string> = {
  dashboard: 'studio.nav.dashboard',
  'group:semantic-assets': 'studio.nav.assets',
  'group:ontology': 'studio.nav.modeling',
  'group:data-integration': 'studio.nav.integration',
  'group:graph': 'studio.nav.graph',
  'group:governance': 'studio.nav.governance',
  'knowledge-bases': 'studio.nav.knowledge',
  'group:system': 'studio.nav.system',
}
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
        <StarMark :size="26" /><span v-if="ui.narrow" class="brand-text"
          ><strong>{{ t('app.title') }}</strong
          ><small>{{ t('navigation.workspace') }}</small></span
        >
      </RouterLink>
      <nav ref="navigation" class="sider-scroll" :aria-label="t('ds.primaryNavigation')">
        <ul v-if="ui.narrow" class="navigation">
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
        <ul v-else class="navigation module-rail">
          <li
            v-for="node in tree"
            :key="node.key"
            class="nav-branch"
            :class="{ 'rail-system': node.adminOnly }"
          >
            <button
              type="button"
              class="rail-item"
              :class="{ 'is-active': moduleActive(node) }"
              :aria-label="t(node.labelKey)"
              :aria-current="moduleActive(node) ? 'page' : undefined"
              :title="t(node.labelKey)"
              @click="openModule(node)"
            >
              <AppIcon v-if="node.icon" :name="node.icon" :size="21" />
              <span v-if="!ui.collapsed">{{ t(railLabels[node.key] ?? node.labelKey) }}</span>
            </button>
          </li>
        </ul>
      </nav>
      <div v-if="ui.narrow && !ui.collapsed" class="sider-foot">
        {{ t('navigation.workspaceHint') }}
      </div>
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
  color: var(--rail-foreground);
  background: var(--rail-background);
}
.brand {
  display: flex;
  flex: none;
  justify-content: center;
  align-items: center;
  height: var(--header-height);
  color: var(--rail-selected);
  text-decoration: none;
}
.brand :deep(svg) {
  color: var(--rail-foreground);
}
.brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.brand-text strong {
  font-size: 14px;
  font-weight: 600;
}
.brand-text small {
  margin-top: 2px;
  font-size: 11px;
  color: var(--rail-foreground);
}
.sider-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px 8px;
}
.navigation {
  padding: 0;
  margin: 0;
  list-style: none;
}
.module-rail {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 100%;
}
.rail-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 7px;
  width: 100%;
  min-height: 60px;
  padding: 9px 2px;
  color: var(--rail-foreground);
  background: none;
  border: 0;
  border-radius: 7px;
}
.rail-item span {
  font-size: 11px;
  line-height: 1.4;
  text-align: center;
  overflow-wrap: anywhere;
}
.rail-item:hover {
  background: var(--rail-active);
  color: var(--rail-selected);
}
.rail-item.is-active {
  background: var(--rail-active);
  color: var(--rail-selected);
  position: relative;
}
.rail-item.is-active::before {
  content: '';
  position: absolute;
  left: -8px;
  width: 3px;
  height: 24px;
  background: var(--rail-indicator);
  border-radius: 0 3px 3px 0;
}
.rail-item:focus-visible {
  outline-color: var(--rail-selected);
  outline-offset: 2px;
}
.rail-system {
  margin-top: auto;
  padding-top: 24px;
}
.sider-foot {
  padding: 16px;
  font-size: 11px;
  line-height: 1.6;
}
@media (max-width: 1023px) {
  .app-sider {
    position: fixed;
    z-index: var(--z-navigation);
    top: 0;
    bottom: 0;
    left: 0;
    width: min(288px, calc(100vw - 48px));
    transition: transform var(--duration-normal);
    box-shadow: var(--shadow-overlay);
  }
  .app-sider.is-collapsed {
    transform: translateX(-105%);
    pointer-events: none;
  }
  .brand {
    justify-content: flex-start;
    gap: 12px;
    padding: 0 20px;
  }
  .sider-scroll {
    padding: 12px;
  }
  .app-sider :deep(.nav-item) {
    color: var(--rail-foreground);
  }
  .app-sider :deep(.nav-item:hover),
  .app-sider :deep(.nav-item.is-active) {
    color: var(--rail-selected);
    background: var(--rail-active);
  }
  .app-sider :deep(.nav-item:focus-visible) {
    outline-color: var(--rail-selected);
  }
}
</style>
