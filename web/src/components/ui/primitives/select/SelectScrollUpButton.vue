<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/select.json; original registry SHA256: 5c2568274e2ab9c42f373cbed8747d3fa4449bb18c0529cebebd5c2b15514b6c. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { ChevronUpIcon } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import type { SelectScrollUpButtonProps } from 'reka-ui'
import { SelectScrollUpButton, useForwardProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<SelectScrollUpButtonProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <SelectScrollUpButton
    data-slot="select-scroll-up-button"
    v-bind="forwardedProps"
    :class="
      cn(
        'bg-popover z-[var(--z-sticky)] flex cursor-default items-center justify-center py-1 [&_svg:not([class*=size-])]:size-[var(--space-4)]',
        props.class,
      )
    "
  >
    <slot>
      <ChevronUpIcon />
    </slot>
  </SelectScrollUpButton>
</template>
