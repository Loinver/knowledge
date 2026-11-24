<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/tooltip.json; original registry SHA256: fe056a94c99234c71b2e9e3f9db387510d371b8ce6d6c9975793fe0ceeda1e64. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { TooltipContentEmits, TooltipContentProps } from 'reka-ui'
import { TooltipArrow, TooltipContent, TooltipPortal, useForwardPropsEmits } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

defineOptions({
  inheritAttrs: false,
})

const props = withDefaults(
  defineProps<TooltipContentProps & { class?: HTMLAttributes['class'] }>(),
  {
    sideOffset: 0,
  },
)

const emits = defineEmits<TooltipContentEmits>()

const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <TooltipPortal>
    <TooltipContent
      data-slot="tooltip-content"
      v-bind="{ ...forwarded, ...$attrs }"
      :class="
        cn(
          'data-[state=instant-open]:animate-in data-[state=instant-open]:fade-in-0 data-[state=instant-open]:zoom-in-95 data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in-0 data-[state=delayed-open]:zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 inline-flex items-center gap-1.5 rounded-[var(--radius-small)] px-3 py-1.5 text-[length:var(--font-caption)] has-data-[slot=kbd]:pr-1.5 **:data-[slot=kbd]:relative **:data-[slot=kbd]:isolate **:data-[slot=kbd]:z-[var(--z-tooltip)] **:data-[slot=kbd]:rounded-[var(--radius-small)] bg-foreground text-background z-[var(--z-tooltip)] w-fit max-w-xs origin-(--reka-tooltip-content-transform-origin)',
          props.class,
        )
      "
    >
      <slot />

      <TooltipArrow
        class="size-[calc(var(--space-1)*2.5)] rotate-45 rounded-[var(--radius-small)] bg-foreground fill-foreground z-[var(--z-tooltip)] translate-y-[calc(-50%_-_2px)]"
      />
    </TooltipContent>
  </TooltipPortal>
</template>
