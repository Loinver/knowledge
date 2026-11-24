<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/sheet.json; original registry SHA256: 50d9ab833ab47e1c15a81bfd4cf77736464b17a29c81a965ff20607054177cab. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { XIcon } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import type { DialogContentEmits, DialogContentProps } from 'reka-ui'
import { DialogClose, DialogContent, DialogPortal, useForwardPropsEmits } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { Button } from '@/components/ui/primitives/button'
import { cn, usePrimitiveI18n } from '@/components/ui/utils'

import SheetOverlay from './SheetOverlay.vue'

interface SheetContentProps extends DialogContentProps {
  class?: HTMLAttributes['class']
  side?: 'top' | 'right' | 'bottom' | 'left'
  showCloseButton?: boolean
}

defineOptions({
  inheritAttrs: false,
})

const props = withDefaults(defineProps<SheetContentProps>(), {
  side: 'right',
  showCloseButton: true,
})
const emits = defineEmits<DialogContentEmits>()

const delegatedProps = reactiveOmit(props, 'class', 'side', 'showCloseButton')

const forwarded = useForwardPropsEmits(delegatedProps, emits)
const { t: primitiveText } = usePrimitiveI18n()
</script>

<template>
  <DialogPortal>
    <SheetOverlay />
    <DialogContent
      data-slot="sheet-content"
      :data-side="side"
      :class="
        cn(
          'bg-popover text-popover-foreground fixed z-[var(--z-dialog)] flex flex-col gap-4 bg-clip-padding text-[length:var(--font-body)] shadow-lg transition duration-200 ease-in-out data-[side=bottom]:inset-x-0 data-[side=bottom]:bottom-0 data-[side=bottom]:h-auto data-[side=bottom]:border-t data-[side=left]:inset-y-0 data-[side=left]:left-0 data-[side=left]:h-full data-[side=left]:w-3/4 data-[side=left]:border-r data-[side=right]:inset-y-0 data-[side=right]:right-0 data-[side=right]:h-full data-[side=right]:w-3/4 data-[side=right]:border-l data-[side=top]:inset-x-0 data-[side=top]:top-0 data-[side=top]:h-auto data-[side=top]:border-b data-[side=left]:sm:max-w-sm data-[side=right]:sm:max-w-sm data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[side=bottom]:data-[state=open]:slide-in-from-bottom-10 data-[side=left]:data-[state=open]:slide-in-from-left-10 data-[side=right]:data-[state=open]:slide-in-from-right-10 data-[side=top]:data-[state=open]:slide-in-from-top-10 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[side=bottom]:data-[state=closed]:slide-out-to-bottom-10 data-[side=left]:data-[state=closed]:slide-out-to-left-10 data-[side=right]:data-[state=closed]:slide-out-to-right-10 data-[side=top]:data-[state=closed]:slide-out-to-top-10',
          props.class,
        )
      "
      v-bind="{ ...$attrs, ...forwarded }"
    >
      <slot />

      <DialogClose v-if="showCloseButton" data-slot="sheet-close" as-child>
        <Button variant="ghost" class="absolute top-3 right-3" size="icon-sm">
          <XIcon />
          <span class="sr-only">{{ primitiveText('close') }}</span>
        </Button>
      </DialogClose>
    </DialogContent>
  </DialogPortal>
</template>
