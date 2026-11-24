<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/collapsible.json; original registry SHA256: 4a6155a921abeabd0de8efbc944dde16bce47652a0a76e08e80fbfc765b132c2. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { CollapsibleContentProps } from 'reka-ui'
import { CollapsibleContent } from 'reka-ui'

const props = defineProps<CollapsibleContentProps>()
</script>

<template>
  <CollapsibleContent data-slot="collapsible-content" v-bind="props">
    <slot />
  </CollapsibleContent>
</template>
