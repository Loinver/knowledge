<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/input-group.json; original registry SHA256: 128d4c1d4a279152f73826699d795b0faa34d308851c92a39b739a5504ebc3e5. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

import type { InputGroupVariants } from '.'
import { inputGroupAddonVariants } from '.'

const props = withDefaults(
  defineProps<{
    align?: InputGroupVariants['align']
    class?: HTMLAttributes['class']
  }>(),
  {
    align: 'inline-start',
  },
)

function handleInputGroupAddonClick(e: MouseEvent) {
  const currentTarget = e.currentTarget as HTMLElement | null
  const target = e.target as HTMLElement | null
  if (target && target.closest('button')) {
    return
  }
  if (currentTarget && currentTarget?.parentElement) {
    currentTarget.parentElement?.querySelector<HTMLElement>('input, textarea')?.focus()
  }
}
</script>

<template>
  <div
    role="group"
    data-slot="input-group-addon"
    :data-align="props.align"
    :class="cn(inputGroupAddonVariants({ align: props.align }), props.class)"
    @click="handleInputGroupAddonClick"
  >
    <slot />
  </div>
</template>
