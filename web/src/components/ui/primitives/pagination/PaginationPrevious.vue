<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/pagination.json; original registry SHA256: fac92217aaf383274e3db4c0918db5ae13f17edb259529d9a7d8c9da193d6589. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { ChevronLeftIcon } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import type { PaginationPrevProps } from 'reka-ui'
import { PaginationPrev, useForwardProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import type { ButtonVariants } from '@/components/ui/primitives/button'
import { buttonVariants } from '@/components/ui/primitives/button'
import { cn, usePrimitiveI18n } from '@/components/ui/utils'

const props = withDefaults(
  defineProps<
    PaginationPrevProps & {
      size?: ButtonVariants['size']
      class?: HTMLAttributes['class']
    }
  >(),
  {
    size: 'default',
  },
)

const delegatedProps = reactiveOmit(props, 'class', 'size')
const forwarded = useForwardProps(delegatedProps)
const { t: primitiveText } = usePrimitiveI18n()
</script>

<template>
  <PaginationPrev
    data-slot="pagination-previous"
    :class="cn(buttonVariants({ variant: 'ghost', size }), 'pl-1.5!', props.class)"
    v-bind="forwarded"
    :aria-label="String($attrs['aria-label'] ?? primitiveText('previous'))"
  >
    <slot>
      <ChevronLeftIcon data-icon="inline-start" class="cn-rtl-flip" />
      <span class="hidden sm:block">{{ primitiveText('previous') }}</span>
    </slot>
  </PaginationPrev>
</template>
