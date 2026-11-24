<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/input-group.json; original registry SHA256: 128d4c1d4a279152f73826699d795b0faa34d308851c92a39b739a5504ebc3e5. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <span
    :class="
      cn(
        'text-muted-foreground gap-2 text-[length:var(--font-body)] [&_svg:not([class*=size-])]:size-[var(--space-4)] flex items-center [&_svg]:pointer-events-none',
        props.class,
      )
    "
  >
    <slot />
  </span>
</template>
