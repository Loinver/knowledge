<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/dropdown-menu.json; original registry SHA256: ef4ef416d50abe38e977e0384bae1125611cc3e67bb47cb7dee2ac36e64ee9e9. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { DropdownMenuTriggerProps } from 'reka-ui'
import { DropdownMenuTrigger, useForwardProps } from 'reka-ui'

const props = defineProps<DropdownMenuTriggerProps>()

const forwardedProps = useForwardProps(props)
</script>

<template>
  <DropdownMenuTrigger data-slot="dropdown-menu-trigger" v-bind="forwardedProps">
    <slot />
  </DropdownMenuTrigger>
</template>
