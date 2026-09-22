<script setup lang="ts">
import { NLayout, NLayoutContent } from 'naive-ui'
import { RouterView } from 'vue-router'

import AppHeader from '@/layout/components/AppHeader.vue'
import AppSider from '@/layout/components/AppSider.vue'
</script>

<template>
  <NLayout class="admin-layout" has-sider>
    <AppSider />
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
.content {
  /* 全站唯一的内容内边距基线，页面内部不再各自重复 padding */
  padding: var(--space-5);
}
</style>
