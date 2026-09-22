<script setup lang="ts">
import { computed } from 'vue'

import { type IconName, iconPaths } from '@/components/icons'

/**
 * 轻量线性图标。
 *
 * 项目不引入图标依赖（依赖许可红线 + 体积），统一内联 SVG：
 * 24x24 视框、`stroke: currentColor`、无填充，随文字颜色与暗色主题自适应。
 */
const props = withDefaults(defineProps<{ name: IconName; size?: number }>(), { size: 18 })

const path = computed(() => iconPaths[props.name])
</script>

<template>
  <svg
    :width="props.size"
    :height="props.size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <path :d="path" />
  </svg>
</template>
