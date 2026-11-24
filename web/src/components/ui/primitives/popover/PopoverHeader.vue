<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/popover.json; original registry SHA256: 3f33d437a9a8b8b9fcacf715da1509907301d509c51664a00ff6b2d577e6be45. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <div
    data-slot="popover-header"
    :class="cn('flex flex-col gap-0.5 text-[length:var(--font-body)]', props.class)"
  >
    <slot />
  </div>
</template>
