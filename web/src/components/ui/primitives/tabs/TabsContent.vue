<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/tabs.json; original registry SHA256: f2c275bc4026050f6d5b447a38a2e3802e55d8adfd27c172c73401339cb7b25f. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { TabsContentProps } from 'reka-ui'
import { TabsContent } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<TabsContentProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <TabsContent
    data-slot="tabs-content"
    :class="cn('text-[length:var(--font-body)] flex-1 outline-none', props.class)"
    v-bind="delegatedProps"
  >
    <slot />
  </TabsContent>
</template>
