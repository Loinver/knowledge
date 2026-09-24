<script setup lang="ts">
import { NLayout, NLayoutContent } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { RouterView } from 'vue-router'

import AppHeader from '@/layout/components/AppHeader.vue'
import AppSider from '@/layout/components/AppSider.vue'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const { t } = useI18n()
</script>

<template>
  <NLayout class="admin-layout" has-sider>
    <AppSider />
    <button
      v-if="!ui.collapsed"
      class="mobile-backdrop"
      type="button"
      :aria-label="t('layout.collapseSider')"
      @click="ui.toggleSider()"
    />
    <NLayout class="admin-main">
      <AppHeader />
      <NLayoutContent class="content" :native-scrollbar="false">
        <RouterView />
      </NLayoutContent>
    </NLayout>
  </NLayout>
</template>

<style scoped>
/*
 * 布局高度链：.admin-layout（定高 100vh）→ 内部滚动容器（height:100%）
 * → 右侧布局 → 顶栏固定 + 内容区吃掉剩余高度。
 *
 * naive-ui 会在每个 NLayout 内部再插一层 `.n-layout-scroll-container`
 * （`height: 100%`）。这条链上任何一环的高度是 auto，后面的百分比就都解析不了，
 * 于是侧栏、内容区会一起塌陷成「内容高度」——短页面上侧栏只覆盖半屏，
 * 长页面上又随内容拉伸。三处关键点缺一不可：
 *   1. 根元素必须定高（height 而非 min-height）；
 *   2. 右侧布局与其滚动容器必须是纵向 flex，顶栏才固定、内容区才能吃掉剩余高度；
 *   3. 内容区必须有确定高度，其内部滚动与页面里的百分比高度才成立。
 */
.admin-layout {
  height: 100vh;
}

.admin-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.admin-main :deep(.n-layout-scroll-container) {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.admin-main :deep(.n-layout-header) {
  flex: none;
}

.content {
  /* 全站唯一的内容内边距基线，页面内部不再各自重复 padding */
  flex: 1;
  min-width: 0;
  min-height: 0;
  padding: var(--space-5);
}
.mobile-backdrop {
  display: none;
}

@media (max-width: 767px) {
  .content {
    padding: var(--space-4);
  }

  .mobile-backdrop {
    position: fixed;
    z-index: 999;
    inset: 0;
    display: block;
    width: 100%;
    height: 100%;
    padding: 0;
    background: rgba(0, 0, 0, 0.42);
    border: 0;
    cursor: pointer;
  }
}
</style>
