<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/sheet.json; original registry SHA256: 50d9ab833ab47e1c15a81bfd4cf77736464b17a29c81a965ff20607054177cab. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { DialogCloseProps } from 'reka-ui'
import { DialogClose } from 'reka-ui'

const props = defineProps<DialogCloseProps>()
</script>

<template>
  <DialogClose data-slot="sheet-close" v-bind="props">
    <slot />
  </DialogClose>
</template>
