<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/dialog.json; original registry SHA256: b1d0a48ef9dc6f71ad128761ceb1a957901306d2e097cd7ee20c703388c5db03. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { DialogClose } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { Button } from '@/components/ui/primitives/button'
import { cn, usePrimitiveI18n } from '@/components/ui/utils'

const props = withDefaults(
  defineProps<{
    class?: HTMLAttributes['class']
    showCloseButton?: boolean
  }>(),
  {
    showCloseButton: false,
  },
)
const { t: primitiveText } = usePrimitiveI18n()
</script>

<template>
  <div
    data-slot="dialog-footer"
    :class="
      cn(
        'bg-muted/50 -mx-4 -mb-4 rounded-b-[var(--radius-overlay)] border-t p-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end',
        props.class,
      )
    "
  >
    <slot />
    <DialogClose v-if="showCloseButton" as-child>
      <Button variant="outline">
        {{ primitiveText('close') }}
      </Button>
    </DialogClose>
  </div>
</template>
