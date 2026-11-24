<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/pagination.json; original registry SHA256: fac92217aaf383274e3db4c0918db5ae13f17edb259529d9a7d8c9da193d6589. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { PaginationRootEmits, PaginationRootProps } from 'reka-ui'
import { PaginationRoot, useForwardPropsEmits } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<
  PaginationRootProps & {
    class?: HTMLAttributes['class']
  }
>()
const emits = defineEmits<PaginationRootEmits>()

const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <PaginationRoot
    v-slot="slotProps"
    data-slot="pagination"
    v-bind="forwarded"
    :class="cn('mx-auto flex w-full justify-center', props.class)"
  >
    <slot v-bind="slotProps" />
  </PaginationRoot>
</template>
