<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/field.json; original registry SHA256: 118c9008651ead02e6e4cf683eccacce193d0bd98f982355e1dc4a44dc669bc2. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = withDefaults(
  defineProps<{
    class?: HTMLAttributes['class']
    variant?: 'legend' | 'label'
  }>(),
  {
    variant: 'legend',
  },
)
</script>

<template>
  <legend
    data-slot="field-legend"
    :data-variant="variant"
    :class="
      cn(
        'mb-1.5 font-medium data-[variant=label]:text-[length:var(--font-body)] data-[variant=legend]:text-[length:var(--font-body)]',
        props.class,
      )
    "
  >
    <slot />
  </legend>
</template>
