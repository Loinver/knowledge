<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/dropdown-menu.json; original registry SHA256: ef4ef416d50abe38e977e0384bae1125611cc3e67bb47cb7dee2ac36e64ee9e9. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { DropdownMenuLabelProps } from 'reka-ui'
import { DropdownMenuLabel, useForwardProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<
  DropdownMenuLabelProps & { class?: HTMLAttributes['class']; inset?: boolean }
>()

const delegatedProps = reactiveOmit(props, 'class', 'inset')
const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <DropdownMenuLabel
    data-slot="dropdown-menu-label"
    :data-inset="inset ? '' : undefined"
    v-bind="forwardedProps"
    :class="
      cn(
        'text-muted-foreground px-1.5 py-1 text-[length:var(--font-caption)] font-medium data-inset:pl-7',
        props.class,
      )
    "
  >
    <slot />
  </DropdownMenuLabel>
</template>
