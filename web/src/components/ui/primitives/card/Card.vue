<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/card.json; original registry SHA256: b92c5cb516bc2300fbedf10c9428a5fa2647b4a8a2516b0eb98ca840a80ff07d. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = withDefaults(
  defineProps<{
    class?: HTMLAttributes['class']
    size?: 'default' | 'sm'
  }>(),
  {
    size: 'default',
  },
)
</script>

<template>
  <div
    data-slot="card"
    :data-size="size"
    :class="
      cn(
        'ring-foreground/10 bg-card text-card-foreground gap-4 overflow-hidden rounded-[var(--radius-panel)] py-4 text-[length:var(--font-body)] ring-1 has-data-[slot=card-footer]:pb-0 has-[>img:first-child]:pt-0 data-[size=sm]:gap-3 data-[size=sm]:py-3 data-[size=sm]:has-data-[slot=card-footer]:pb-0 *:[img:first-child]:rounded-t-[var(--radius-panel)] *:[img:last-child]:rounded-b-[var(--radius-panel)] group/card flex flex-col',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>
