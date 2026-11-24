<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/combobox.json; original registry SHA256: fbe5e77d4dbee65a561026fcaa51d0735ab0aa42319741f009fe03cb69c13cd1. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { ComboboxViewportProps } from 'reka-ui'
import { ComboboxViewport, useForwardProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<ComboboxViewportProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')

const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <ComboboxViewport
    data-slot="combobox-viewport"
    v-bind="forwarded"
    :class="
      cn(
        'no-scrollbar max-h-[min(calc(--spacing(72)---spacing(9)),calc(var(--available-height)---spacing(9)))] scroll-py-1 overflow-y-auto p-1 data-empty:p-0',
        props.class,
      )
    "
  >
    <slot />
  </ComboboxViewport>
</template>
