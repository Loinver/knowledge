<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/tooltip.json; original registry SHA256: fe056a94c99234c71b2e9e3f9db387510d371b8ce6d6c9975793fe0ceeda1e64. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { TooltipRootEmits, TooltipRootProps } from 'reka-ui'
import { TooltipRoot, useForwardPropsEmits } from 'reka-ui'

const props = defineProps<TooltipRootProps>()
const emits = defineEmits<TooltipRootEmits>()

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <TooltipRoot v-slot="slotProps" data-slot="tooltip" v-bind="forwarded">
    <slot v-bind="slotProps" />
  </TooltipRoot>
</template>
