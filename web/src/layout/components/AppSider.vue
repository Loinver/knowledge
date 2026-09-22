<script setup lang="ts">
import { NLayoutSider, NMenu } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

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
    <RouterLink class="brand" :to="{ name: 'dashboard' }">
      <span class="brand-mark">{{ t('app.shortName') }}</span>
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
.brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  height: var(--header-height);
  padding: 0 var(--space-4);
  overflow: hidden;
  color: var(--text);
  text-decoration: none;
  white-space: nowrap;
  border-bottom: 1px solid var(--border);
}
.brand-mark {
  display: inline-flex;
  flex: 0 0 28px;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  color: #fff;
  font-size: var(--font-caption);
  font-weight: 700;
  background: var(--pri);
  border-radius: var(--radius-medium);
}
.brand-text {
  font-size: 16px;
  font-weight: 600;
}
</style>
