<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/tooltip.json; original registry SHA256: fe056a94c99234c71b2e9e3f9db387510d371b8ce6d6c9975793fe0ceeda1e64. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { TooltipProviderProps } from 'reka-ui'
import { TooltipProvider } from 'reka-ui'

const props = withDefaults(defineProps<TooltipProviderProps>(), {
  delayDuration: 0,
})
</script>

<template>
  <TooltipProvider v-bind="props">
    <slot />
  </TooltipProvider>
</template>
