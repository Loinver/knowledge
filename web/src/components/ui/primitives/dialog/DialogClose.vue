<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/dialog.json; original registry SHA256: b1d0a48ef9dc6f71ad128761ceb1a957901306d2e097cd7ee20c703388c5db03. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { DialogCloseProps } from 'reka-ui'
import { DialogClose } from 'reka-ui'

const props = defineProps<DialogCloseProps>()
</script>

<template>
  <DialogClose data-slot="dialog-close" v-bind="props">
    <slot />
  </DialogClose>
</template>
