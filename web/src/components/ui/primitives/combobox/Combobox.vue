<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/combobox.json; original registry SHA256: fbe5e77d4dbee65a561026fcaa51d0735ab0aa42319741f009fe03cb69c13cd1. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { ComboboxRootEmits, ComboboxRootProps } from 'reka-ui'
import { ComboboxRoot, useForwardPropsEmits } from 'reka-ui'

const props = defineProps<ComboboxRootProps>()
const emits = defineEmits<ComboboxRootEmits>()

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <ComboboxRoot v-slot="slotProps" data-slot="combobox" v-bind="forwarded">
    <slot v-bind="slotProps" />
  </ComboboxRoot>
</template>
