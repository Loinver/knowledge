<script setup lang="ts">
import { NLayoutSider, NMenu } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import StarMark from '@/components/StarMark.vue'
import { useNavigation } from '@/layout/useNavigation'
import { useUiStore } from '@/stores/ui'

const { t } = useI18n()
const ui = useUiStore()
const { menuOptions, activeKey, expandedKeys, selectMenu } = useNavigation()

function updateExpanded(keys: string[]) {
  // 侧栏自己触发的变化也要接受，否则用户手动展开分组会立刻被回滚
  expandedKeys.value = keys
}
</script>

<template>
  <NLayoutSider
    bordered
    collapse-mode="width"
    :collapsed="ui.collapsed"
    :collapsed-width="64"
    :width="220"
    :native-scrollbar="false"
    class="app-sider"
  >
    <RouterLink
      class="brand"
      :to="{ name: 'dashboard' }"
      :aria-label="t('app.title')"
      :title="ui.collapsed ? t('app.title') : undefined"
    >
      <StarMark :size="22" />
      <span v-show="!ui.collapsed" class="brand-text">{{ t('app.title') }}</span>
    </RouterLink>
    <NMenu
      :value="activeKey"
      :options="menuOptions"
      :collapsed="ui.collapsed"
      :collapsed-width="64"
      :collapsed-icon-size="20"
      :indent="18"
      :expanded-keys="expandedKeys"
      @update:value="selectMenu"
      @update:expanded-keys="updateExpanded"
    />
  </NLayoutSider>
</template>

<style scoped>
.app-sider {
  display: flex;
  flex-direction: column;
}

.app-sider :deep(.n-layout-sider-scroll-container) {
  min-width: 0;
}

/* 品牌行与顶栏等高，两者底边对齐形成一条贯通的分隔线 */
.brand {
  display: flex;
  gap: 9px;
  align-items: center;
  height: var(--header-height);
  padding: 0 var(--space-4);
  overflow: hidden;
  color: var(--text);
  text-decoration: none;
  white-space: nowrap;
  border-bottom: 1px solid var(--border-subtle);
}

.brand-text {
  overflow: hidden;
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.3px;
  text-overflow: ellipsis;
}

@media (max-width: 767px) {
  .app-sider {
    position: fixed;
    z-index: 1000;
    inset: 0 auto 0 0;
    width: var(--sider-width) !important;
    max-width: calc(100vw - 32px);
    transform: translateX(0);
    transition: transform var(--dur-base) var(--ease-out);
  }

  .app-sider.n-layout-sider--collapsed {
    width: var(--sider-width) !important;
    transform: translateX(-100%);
  }
}
</style>
