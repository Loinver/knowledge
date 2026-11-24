<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/radio-group.json; original registry SHA256: c78b007aafb35cb8dfaa2265900f0883eb94369db6d2b295bd18c143c64ed77d. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { RadioGroupRootEmits, RadioGroupRootProps } from 'reka-ui'
import { RadioGroupRoot, useForwardPropsEmits } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<RadioGroupRootProps & { class?: HTMLAttributes['class'] }>()
const emits = defineEmits<RadioGroupRootEmits>()

const delegatedProps = reactiveOmit(props, 'class')

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <RadioGroupRoot
    v-slot="slotProps"
    data-slot="radio-group"
    :class="cn('grid gap-2 w-full', props.class)"
    v-bind="forwarded"
  >
    <slot v-bind="slotProps" />
  </RadioGroupRoot>
</template>
