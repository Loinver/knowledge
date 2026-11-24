<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/field.json; original registry SHA256: 118c9008651ead02e6e4cf683eccacce193d0bd98f982355e1dc4a44dc669bc2. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { Label } from '@/components/ui/primitives/label'
import { cn } from '@/components/ui/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <Label
    data-slot="field-label"
    :class="
      cn(
        'has-data-[state=checked]:bg-primary/5 has-data-[state=checked]:border-primary/30 dark:has-data-[state=checked]:border-primary/20 dark:has-data-[state=checked]:bg-primary/10 gap-2 group-data-[disabled=true]/field:opacity-50 has-[>[data-slot=field]]:rounded-[var(--radius-control)] has-[>[data-slot=field]]:border *:data-[slot=field]:p-2.5 group/field-label peer/field-label flex w-fit leading-snug',
        'has-[>[data-slot=field]]:w-full has-[>[data-slot=field]]:flex-col',
        props.class,
      )
    "
  >
    <slot />
  </Label>
</template>
