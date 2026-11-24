<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/pagination.json; original registry SHA256: fac92217aaf383274e3db4c0918db5ae13f17edb259529d9a7d8c9da193d6589. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import type { ButtonVariants } from '@/components/ui/primitives/button'
import { buttonVariants } from '@/components/ui/primitives/button'
import { cn } from '@/components/ui/utils'

const props = withDefaults(
  defineProps<{
    href?: string
    size?: ButtonVariants['size']
    isActive?: boolean
    class?: HTMLAttributes['class']
  }>(),
  {
    size: 'icon',
    isActive: false,
  },
)
</script>

<template>
  <a
    :href="href"
    data-slot="pagination-link"
    :data-active="isActive ? '' : undefined"
    :aria-current="isActive ? 'page' : undefined"
    :class="
      cn(
        buttonVariants({
          variant: isActive ? 'outline' : 'ghost',
          size,
        }),
        '',
        props.class,
      )
    "
  >
    <slot />
  </a>
</template>
