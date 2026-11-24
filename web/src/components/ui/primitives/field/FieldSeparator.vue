<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/field.json; original registry SHA256: 118c9008651ead02e6e4cf683eccacce193d0bd98f982355e1dc4a44dc669bc2. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { Separator } from '@/components/ui/primitives/separator'
import { cn } from '@/components/ui/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <div
    data-slot="field-separator"
    :data-content="!!$slots.default"
    :class="
      cn(
        '-my-2 h-[calc(var(--space-1)*5)] text-[length:var(--font-body)] group-data-[variant=outline]/field-group:-mb-2 relative',
        props.class,
      )
    "
  >
    <Separator class="absolute inset-0 top-1/2" />
    <span
      v-if="$slots.default"
      class="text-muted-foreground px-2 relative mx-auto block w-fit bg-background"
      data-slot="field-separator-content"
    >
      <slot />
    </span>
  </div>
</template>
