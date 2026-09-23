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
    <NLayout>
      <AppHeader />
      <NLayoutContent class="content" :native-scrollbar="false">
        <RouterView />
      </NLayoutContent>
    </NLayout>
  </NLayout>
</template>

<style scoped>
.admin-layout {
  min-height: 100vh;
}
.admin-layout > .n-layout {
  min-width: 0;
}
.content {
  /* 全站唯一的内容内边距基线，页面内部不再各自重复 padding */
  padding: var(--space-5);
  min-width: 0;
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
