<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/combobox.json; original registry SHA256: fbe5e77d4dbee65a561026fcaa51d0735ab0aa42319741f009fe03cb69c13cd1. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { ComboboxGroupProps } from 'reka-ui'
import { ComboboxGroup, ComboboxLabel } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<
  ComboboxGroupProps & {
    class?: HTMLAttributes['class']
    heading?: string
  }
>()

const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <ComboboxGroup
    data-slot="combobox-group"
    v-bind="delegatedProps"
    :class="cn('overflow-hidden text-foreground', props.class)"
  >
    <ComboboxLabel
      v-if="heading"
      class="text-muted-foreground px-2 py-1.5 text-[length:var(--font-caption)]"
    >
      {{ heading }}
    </ComboboxLabel>
    <slot />
  </ComboboxGroup>
</template>
