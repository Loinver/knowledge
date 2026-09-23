<script setup lang="ts">
/**
 * 认证页的标题区。
 *
 * 四个认证页（登录 / 注册 / 忘记 / 重置）共用同一版式：
 * 19px 标题 + 一行灰色说明，让右侧表单区有稳定的视觉起点。
 */
defineProps<{ title: string; subtitle?: string }>()
</script>

<template>
  <header class="auth-heading">
    <h2>{{ title }}</h2>
    <p v-if="subtitle">{{ subtitle }}</p>
  </header>
</template>

<style scoped>
.auth-heading {
  margin-bottom: var(--space-5);
}

.auth-heading h2 {
  margin: 0 0 6px;
  font-size: 19px;
  font-weight: 500;
  line-height: 1.4;
}

.auth-heading p {
  margin: 0;
  color: var(--text-tertiary);
  font-size: var(--font-caption);
  line-height: 1.7;
}
</style>
