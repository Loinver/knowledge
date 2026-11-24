<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/dropdown-menu.json; original registry SHA256: ef4ef416d50abe38e977e0384bae1125611cc3e67bb47cb7dee2ac36e64ee9e9. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { ChevronRightIcon } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import type { DropdownMenuSubTriggerProps } from 'reka-ui'
import { DropdownMenuSubTrigger, useForwardProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<
  DropdownMenuSubTriggerProps & { class?: HTMLAttributes['class']; inset?: boolean }
>()

const delegatedProps = reactiveOmit(props, 'class', 'inset')
const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <DropdownMenuSubTrigger
    data-slot="dropdown-menu-sub-trigger"
    :data-inset="inset ? '' : undefined"
    v-bind="forwardedProps"
    :class="
      cn(
        'focus:bg-accent focus:text-accent-foreground data-[state=open]:bg-accent data-[state=open]:text-accent-foreground not-data-[variant=destructive]:focus:**:text-accent-foreground gap-1.5 rounded-[var(--radius-control)] px-1.5 py-1 text-[length:var(--font-body)] data-inset:pl-7 [&_svg:not([class*=size-])]:size-[var(--space-4)] flex cursor-default items-center outline-hidden select-none [&_svg]:pointer-events-none [&_svg]:shrink-0',
        props.class,
      )
    "
  >
    <slot />
    <ChevronRightIcon class="cn-rtl-flip ml-auto" />
  </DropdownMenuSubTrigger>
</template>
