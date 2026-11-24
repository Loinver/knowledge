<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/combobox.json; original registry SHA256: fbe5e77d4dbee65a561026fcaa51d0735ab0aa42319741f009fe03cb69c13cd1. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { SearchIcon } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import type { ComboboxInputEmits, ComboboxInputProps } from 'reka-ui'
import { ComboboxInput, useForwardPropsEmits } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { InputGroup, InputGroupAddon } from '@/components/ui/primitives/input-group'
import { cn } from '@/components/ui/utils'

defineOptions({
  inheritAttrs: false,
})

const props = defineProps<
  ComboboxInputProps & {
    class?: HTMLAttributes['class']
  }
>()

const emits = defineEmits<ComboboxInputEmits>()

const delegatedProps = reactiveOmit(props, 'class')

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <InputGroup class="w-auto">
    <InputGroupAddon>
      <SearchIcon class="size-[var(--space-4)] shrink-0 opacity-50" />
    </InputGroupAddon>
    <ComboboxInput
      data-slot="combobox-input"
      :class="
        cn('flex-1 outline-hidden disabled:cursor-not-allowed disabled:opacity-50', props.class)
      "
      v-bind="{ ...$attrs, ...forwarded }"
    />
  </InputGroup>
</template>
