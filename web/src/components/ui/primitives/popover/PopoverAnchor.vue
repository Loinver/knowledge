<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/popover.json; original registry SHA256: 3f33d437a9a8b8b9fcacf715da1509907301d509c51664a00ff6b2d577e6be45. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { PopoverAnchorProps } from 'reka-ui'
import { PopoverAnchor } from 'reka-ui'

const props = defineProps<PopoverAnchorProps>()
</script>

<template>
  <PopoverAnchor data-slot="popover-anchor" v-bind="props">
    <slot />
  </PopoverAnchor>
</template>
