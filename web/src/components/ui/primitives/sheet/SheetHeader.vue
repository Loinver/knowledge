<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/sheet.json; original registry SHA256: 50d9ab833ab47e1c15a81bfd4cf77736464b17a29c81a965ff20607054177cab. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<{ class?: HTMLAttributes['class'] }>()
</script>

<template>
  <div data-slot="sheet-header" :class="cn('gap-0.5 p-4 flex flex-col', props.class)">
    <slot />
  </div>
</template>
