<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/combobox.json; original registry SHA256: fbe5e77d4dbee65a561026fcaa51d0735ab0aa42319741f009fe03cb69c13cd1. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { ComboboxItemIndicatorProps } from 'reka-ui'
import { ComboboxItemIndicator, useForwardProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<ComboboxItemIndicatorProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')

const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <ComboboxItemIndicator
    data-slot="combobox-item-indicator"
    v-bind="forwarded"
    :class="
      cn(
        'pointer-events-none absolute right-2 flex size-[var(--space-4)] items-center justify-center',
        props.class,
      )
    "
  >
    <slot />
  </ComboboxItemIndicator>
</template>
