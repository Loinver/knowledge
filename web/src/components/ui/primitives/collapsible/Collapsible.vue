<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/collapsible.json; original registry SHA256: 4a6155a921abeabd0de8efbc944dde16bce47652a0a76e08e80fbfc765b132c2. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { CollapsibleRootEmits, CollapsibleRootProps } from 'reka-ui'
import { CollapsibleRoot, useForwardPropsEmits } from 'reka-ui'

const props = defineProps<CollapsibleRootProps>()
const emits = defineEmits<CollapsibleRootEmits>()

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <CollapsibleRoot v-slot="slotProps" data-slot="collapsible" v-bind="forwarded">
    <slot v-bind="slotProps" />
  </CollapsibleRoot>
</template>
