<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/radio-group.json; original registry SHA256: c78b007aafb35cb8dfaa2265900f0883eb94369db6d2b295bd18c143c64ed77d. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { CircleIcon } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import type { RadioGroupItemProps } from 'reka-ui'
import { RadioGroupIndicator, RadioGroupItem, useForwardProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<RadioGroupItemProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <RadioGroupItem
    data-slot="radio-group-item"
    v-bind="forwardedProps"
    :class="
      cn(
        'border-input dark:bg-input/30 data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground dark:data-[state=checked]:bg-primary data-[state=checked]:border-primary aria-invalid:aria-checked:border-primary aria-invalid:border-destructive focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 dark:aria-invalid:border-destructive/50 flex size-[var(--space-4)] rounded-[var(--radius-pill)] focus-visible:ring-3 aria-invalid:ring-3 group/radio-group-item peer relative aspect-square shrink-0 border outline-none after:absolute after:-inset-x-3 after:-inset-y-2 disabled:cursor-not-allowed disabled:opacity-50',
        props.class,
      )
    "
  >
    <RadioGroupIndicator
      data-slot="radio-group-indicator"
      class="flex size-[var(--space-4)] items-center justify-center"
    >
      <slot>
        <CircleIcon
          class="bg-primary-foreground absolute top-1/2 left-1/2 size-[var(--space-2)] -translate-x-1/2 -translate-y-1/2 rounded-[var(--radius-pill)]"
        />
      </slot>
    </RadioGroupIndicator>
  </RadioGroupItem>
</template>
