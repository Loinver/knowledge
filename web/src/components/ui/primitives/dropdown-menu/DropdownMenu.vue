<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/dropdown-menu.json; original registry SHA256: ef4ef416d50abe38e977e0384bae1125611cc3e67bb47cb7dee2ac36e64ee9e9. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { DropdownMenuRootEmits, DropdownMenuRootProps } from 'reka-ui'
import { DropdownMenuRoot, useForwardPropsEmits } from 'reka-ui'

const props = defineProps<DropdownMenuRootProps>()
const emits = defineEmits<DropdownMenuRootEmits>()

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <DropdownMenuRoot v-slot="slotProps" data-slot="dropdown-menu" v-bind="forwarded">
    <slot v-bind="slotProps" />
  </DropdownMenuRoot>
</template>
