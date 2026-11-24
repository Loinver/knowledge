<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/tabs.json; original registry SHA256: f2c275bc4026050f6d5b447a38a2e3802e55d8adfd27c172c73401339cb7b25f. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { TabsListProps } from 'reka-ui'
import { TabsList } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

import type { TabsListVariants } from '.'
import { tabsListVariants } from '.'

const props = withDefaults(
  defineProps<
    TabsListProps & {
      class?: HTMLAttributes['class']
      variant?: TabsListVariants['variant']
    }
  >(),
  {
    variant: 'default',
  },
)

const delegatedProps = reactiveOmit(props, 'class', 'variant')
</script>

<template>
  <TabsList
    data-slot="tabs-list"
    :data-variant="variant"
    v-bind="delegatedProps"
    :class="cn(tabsListVariants({ variant }), props.class)"
  >
    <slot />
  </TabsList>
</template>
