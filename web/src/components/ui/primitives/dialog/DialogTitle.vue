<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/dialog.json; original registry SHA256: b1d0a48ef9dc6f71ad128761ceb1a957901306d2e097cd7ee20c703388c5db03. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { DialogTitleProps } from 'reka-ui'
import { DialogTitle, useForwardProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<DialogTitleProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <DialogTitle
    data-slot="dialog-title"
    v-bind="forwardedProps"
    :class="
      cn('text-[length:var(--font-h2)] leading-none font-medium cn-font-heading', props.class)
    "
  >
    <slot />
  </DialogTitle>
</template>
