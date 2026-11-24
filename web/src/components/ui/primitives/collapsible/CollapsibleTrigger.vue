<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/collapsible.json; original registry SHA256: 4a6155a921abeabd0de8efbc944dde16bce47652a0a76e08e80fbfc765b132c2. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { CollapsibleTriggerProps } from 'reka-ui'
import { CollapsibleTrigger } from 'reka-ui'

const props = defineProps<CollapsibleTriggerProps>()
</script>

<template>
  <CollapsibleTrigger data-slot="collapsible-trigger" v-bind="props">
    <slot />
  </CollapsibleTrigger>
</template>
