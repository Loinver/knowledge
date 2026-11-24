<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/dialog.json; original registry SHA256: b1d0a48ef9dc6f71ad128761ceb1a957901306d2e097cd7ee20c703388c5db03. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { DialogDescriptionProps } from 'reka-ui'
import { DialogDescription, useForwardProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<DialogDescriptionProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <DialogDescription
    data-slot="dialog-description"
    v-bind="forwardedProps"
    :class="
      cn(
        'text-muted-foreground *:[a]:hover:text-foreground text-[length:var(--font-body)] *:[a]:underline *:[a]:underline-offset-3',
        props.class,
      )
    "
  >
    <slot />
  </DialogDescription>
</template>
