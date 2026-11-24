<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/table.json; original registry SHA256: 0a72dcee002588a7e031379ce632a65ff7eb0f4479ea87f75678db4f48e822a3. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <th
    data-slot="table-head"
    :class="
      cn(
        'text-foreground h-[calc(var(--space-1)*10)] px-2 text-left align-middle font-medium whitespace-nowrap [&:has([role=checkbox])]:pr-0',
        props.class,
      )
    "
  >
    <slot />
  </th>
</template>
