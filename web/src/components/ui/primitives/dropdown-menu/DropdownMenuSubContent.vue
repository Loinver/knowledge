<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/dropdown-menu.json; original registry SHA256: ef4ef416d50abe38e977e0384bae1125611cc3e67bb47cb7dee2ac36e64ee9e9. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { DropdownMenuSubContentEmits, DropdownMenuSubContentProps } from 'reka-ui'
import { DropdownMenuSubContent, useForwardPropsEmits } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<DropdownMenuSubContentProps & { class?: HTMLAttributes['class'] }>()
const emits = defineEmits<DropdownMenuSubContentEmits>()

const delegatedProps = reactiveOmit(props, 'class')

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <DropdownMenuSubContent
    data-slot="dropdown-menu-sub-content"
    v-bind="forwarded"
    :class="
      cn(
        'data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 ring-foreground/10 bg-popover text-popover-foreground min-w-[calc(var(--space-1)*24)] rounded-[var(--radius-control)] p-1 shadow-lg ring-1 duration-100 cn-menu-target cn-menu-translucent z-[var(--z-popover)] max-w-(--reka-dropdown-menu-content-available-width) origin-(--reka-dropdown-menu-content-transform-origin) overflow-hidden',
        props.class,
      )
    "
  >
    <slot />
  </DropdownMenuSubContent>
</template>
