<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/table.json; original registry SHA256: 0a72dcee002588a7e031379ce632a65ff7eb0f4479ea87f75678db4f48e822a3. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

import TableCell from './TableCell.vue'
import TableRow from './TableRow.vue'

const props = withDefaults(
  defineProps<{
    class?: HTMLAttributes['class']
    colspan?: number
  }>(),
  {
    colspan: 1,
  },
)

const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <TableRow>
    <TableCell
      :class="
        cn(
          'p-4 whitespace-nowrap align-middle text-[length:var(--font-body)] text-foreground',
          props.class,
        )
      "
      v-bind="delegatedProps"
    >
      <div class="flex items-center justify-center py-10">
        <slot />
      </div>
    </TableCell>
  </TableRow>
</template>
