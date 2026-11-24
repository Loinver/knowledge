<script setup lang="ts">
import { computed } from 'vue'

import { Badge } from './primitives/badge'
const props = defineProps<{
  type?: 'default' | 'primary' | 'success' | 'info' | 'warning' | 'error'
  size?: string
  round?: boolean
  bordered?: boolean
}>()
const color = computed(
  () =>
    `var(--${{ success: 'status-pass', warning: 'status-not-run', error: 'status-violation', info: 'status-info', primary: 'action-primary', default: 'foreground-secondary' }[props.type || 'default']})`,
)
</script>
<template>
  <Badge
    variant="outline"
    class="ui-tag"
    :style="{ '--tag-color': color, borderRadius: round ? 'var(--radius-pill)' : undefined }"
    ><slot
  /></Badge>
</template>
