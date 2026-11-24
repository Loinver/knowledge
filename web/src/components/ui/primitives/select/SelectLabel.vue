<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/select.json; original registry SHA256: 5c2568274e2ab9c42f373cbed8747d3fa4449bb18c0529cebebd5c2b15514b6c. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { SelectLabelProps } from 'reka-ui'
import { SelectLabel } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<SelectLabelProps & { class?: HTMLAttributes['class'] }>()
</script>

<template>
  <SelectLabel
    data-slot="select-label"
    :class="cn('text-muted-foreground px-1.5 py-1 text-[length:var(--font-caption)]', props.class)"
  >
    <slot />
  </SelectLabel>
</template>
