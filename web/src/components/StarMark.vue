<script setup lang="ts">
/**
 * 品牌标识「星图」：中心节点 + 四个语义节点 + 连线。
 *
 * 四个外圈节点分别取图谱语义色（实体 / 直接关系 / 派生边 / 证据），
 * 与 `tokens.css` 的 `--g-*` 同源——品牌即产品语言本身。
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
    <circle cx="16" cy="16" r="3" fill="var(--g-entity)" />
    <circle cx="6" cy="7" r="2" fill="var(--g-relation)" />
    <circle cx="27" cy="9" r="2" fill="var(--g-derived)" />
    <circle cx="7" cy="26" r="2" fill="var(--g-evidence)" />
    <circle cx="26" cy="25" r="2" fill="var(--g-current)" />
    <path
      d="M16 16L6 7M16 16L27 9M16 16L7 26M16 16L26 25"
      stroke="var(--border-strong)"
      stroke-width="1"
    />
  </svg>
</template>

<style scoped>
.star-mark {
  display: block;
  flex: none;
}
</style>
