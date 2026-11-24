<script setup lang="ts">
import { computed } from 'vue'
const props = withDefaults(
  defineProps<{
    vertical?: boolean
    wrap?: boolean
    size?: number | string | [number, number]
    align?: string
    justify?: string
  }>(),
  { wrap: true, size: 'small' },
)
const gap = computed(() =>
  typeof props.size === 'number'
    ? `${props.size}px`
    : Array.isArray(props.size)
      ? props.size.map((value) => `${value}px`).join(' ')
      : { small: 'var(--space-2)', medium: 'var(--space-3)', large: 'var(--space-4)' }[
          props.size
        ] || props.size,
)
</script>
<template>
  <div
    class="ui-space"
    :style="{
      display: 'flex',
      gap,
      flexDirection: vertical ? 'column' : 'row',
      flexWrap: wrap ? 'wrap' : 'nowrap',
      alignItems: align || (vertical ? 'stretch' : 'center'),
      justifyContent: justify,
      minWidth: 0,
    }"
  >
    <slot />
  </div>
</template>
