<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/field.json; original registry SHA256: 118c9008651ead02e6e4cf683eccacce193d0bd98f982355e1dc4a44dc669bc2. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <div
    data-slot="field-label"
    :class="
      cn(
        'gap-2 text-[length:var(--font-body)] font-medium group-data-[disabled=true]/field:opacity-50 flex w-fit items-center leading-snug',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>
