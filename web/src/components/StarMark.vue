<script setup lang="ts">
/**
 * 知识工作室标识：四块可组合的知识单元，以连接线表达语义关系。
 * 继承宿主前景色，保证深绿导航、浅色和暗色认证页面均可辨认。
 */
withDefaults(defineProps<{ size?: number }>(), { size: 28 })
</script>

<template>
  <svg
    class="star-mark"
    :width="size"
    :height="size"
    viewBox="0 0 32 32"
    fill="none"
    role="img"
    aria-hidden="true"
  >
    <path d="M5 5h9v9H5zM18 18h9v9h-9zM5 19h6v8H5zM20 5h7v6h-7z" fill="currentColor" />
    <path d="m13 10 9 12M9 14v5M18 23h-7" stroke="currentColor" stroke-width="2" />
  </svg>
</template>

<style scoped>
.star-mark {
  display: block;
  flex: none;
}
</style>
