<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/pagination.json; original registry SHA256: fac92217aaf383274e3db4c0918db5ae13f17edb259529d9a7d8c9da193d6589. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { PaginationListProps } from 'reka-ui'
import { PaginationList } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<PaginationListProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <PaginationList
    v-slot="slotProps"
    data-slot="pagination-content"
    v-bind="delegatedProps"
    :class="cn('gap-0.5 flex items-center', props.class)"
  >
    <slot v-bind="slotProps" />
  </PaginationList>
</template>
