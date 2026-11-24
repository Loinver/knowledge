<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/select.json; original registry SHA256: 5c2568274e2ab9c42f373cbed8747d3fa4449bb18c0529cebebd5c2b15514b6c. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { SelectItemTextProps } from 'reka-ui'
import { SelectItemText } from 'reka-ui'

const props = defineProps<SelectItemTextProps>()
</script>

<template>
  <SelectItemText data-slot="select-item-text" v-bind="props">
    <slot />
  </SelectItemText>
</template>
