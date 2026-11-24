<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/sheet.json; original registry SHA256: 50d9ab833ab47e1c15a81bfd4cf77736464b17a29c81a965ff20607054177cab. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { DialogTriggerProps } from 'reka-ui'
import { DialogTrigger } from 'reka-ui'

const props = defineProps<DialogTriggerProps>()
</script>

<template>
  <DialogTrigger data-slot="sheet-trigger" v-bind="props">
    <slot />
  </DialogTrigger>
</template>
