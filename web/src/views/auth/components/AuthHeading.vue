<script setup lang="ts">
/**
 * 认证页的标题区。
 *
 * 四个认证页（登录 / 注册 / 忘记 / 重置）共用同一版式：
 * 身份标题 + 一行任务说明，让右侧表单区有稳定的视觉起点。
 */
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
defineProps<{ title: string; subtitle?: string }>()
</script>

<template>
  <header class="auth-heading">
    <span class="auth-eyebrow">{{ t('operationsUi.authPurpose') }}</span>
    <h1>{{ title }}</h1>
    <p v-if="subtitle">{{ subtitle }}</p>
  </header>
</template>

<style scoped>
.auth-heading {
  margin-bottom: 28px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border);
}
.auth-eyebrow {
  font-size: 11px;
  color: var(--text-secondary);
  letter-spacing: 0.06em;
}
.auth-heading h1 {
  margin: 8px 0 0;
  color: var(--text-primary, var(--text));
  font-size: 24px;
  font-weight: 600;
  line-height: 1.4;
}
.auth-heading p {
  margin: 10px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.7;
}
</style>
