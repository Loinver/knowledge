<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/dialog.json; original registry SHA256: b1d0a48ef9dc6f71ad128761ceb1a957901306d2e097cd7ee20c703388c5db03. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { DialogTriggerProps } from 'reka-ui'
import { DialogTrigger } from 'reka-ui'

const props = defineProps<DialogTriggerProps>()
</script>

<template>
  <DialogTrigger data-slot="dialog-trigger" v-bind="props">
    <slot />
  </DialogTrigger>
</template>
