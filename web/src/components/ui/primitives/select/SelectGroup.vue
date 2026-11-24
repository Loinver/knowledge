<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/select.json; original registry SHA256: 5c2568274e2ab9c42f373cbed8747d3fa4449bb18c0529cebebd5c2b15514b6c. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { SelectGroupProps } from 'reka-ui'
import { SelectGroup } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<SelectGroupProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <SelectGroup
    data-slot="select-group"
    v-bind="delegatedProps"
    :class="cn('scroll-my-1 p-1', props.class)"
  >
    <slot />
  </SelectGroup>
</template>
