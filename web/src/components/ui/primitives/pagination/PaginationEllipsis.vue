<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/pagination.json; original registry SHA256: fac92217aaf383274e3db4c0918db5ae13f17edb259529d9a7d8c9da193d6589. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { MoreHorizontalIcon } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import type { PaginationEllipsisProps } from 'reka-ui'
import { PaginationEllipsis } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn, usePrimitiveI18n } from '@/components/ui/utils'

const props = defineProps<PaginationEllipsisProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')
const { t: primitiveText } = usePrimitiveI18n()
</script>

<template>
  <PaginationEllipsis
    data-slot="pagination-ellipsis"
    v-bind="delegatedProps"
    :class="
      cn(
        'size-[var(--space-6)] [&_svg:not([class*=size-])]:size-[var(--space-4)] flex items-center justify-center',
        props.class,
      )
    "
  >
    <slot>
      <MoreHorizontalIcon />
      <span class="sr-only">{{ primitiveText('more') }}</span>
    </slot>
  </PaginationEllipsis>
</template>
