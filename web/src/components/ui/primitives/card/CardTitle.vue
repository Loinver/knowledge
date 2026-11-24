<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/card.json; original registry SHA256: b92c5cb516bc2300fbedf10c9428a5fa2647b4a8a2516b0eb98ca840a80ff07d. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <div
    data-slot="card-title"
    :class="
      cn(
        'text-[length:var(--font-h2)] leading-snug font-medium group-data-[size=sm]/card:text-[length:var(--font-body)] cn-font-heading',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>
