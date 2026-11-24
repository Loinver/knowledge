<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/pagination.json; original registry SHA256: fac92217aaf383274e3db4c0918db5ae13f17edb259529d9a7d8c9da193d6589. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { ChevronRightIcon } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import type { PaginationNextProps } from 'reka-ui'
import { PaginationNext, useForwardProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import type { ButtonVariants } from '@/components/ui/primitives/button'
import { buttonVariants } from '@/components/ui/primitives/button'
import { cn, usePrimitiveI18n } from '@/components/ui/utils'

const props = withDefaults(
  defineProps<
    PaginationNextProps & {
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
  <PaginationNext
    data-slot="pagination-next"
    :class="cn(buttonVariants({ variant: 'ghost', size }), 'pr-1.5!', props.class)"
    v-bind="forwarded"
    :aria-label="String($attrs['aria-label'] ?? primitiveText('next'))"
  >
    <slot>
      <span class="hidden sm:block">{{ primitiveText('next') }}</span>
      <ChevronRightIcon data-icon="inline-end" class="cn-rtl-flip" />
    </slot>
  </PaginationNext>
</template>
