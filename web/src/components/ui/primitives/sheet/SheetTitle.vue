<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/sheet.json; original registry SHA256: 50d9ab833ab47e1c15a81bfd4cf77736464b17a29c81a965ff20607054177cab. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { DialogTitleProps } from 'reka-ui'
import { DialogTitle } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<DialogTitleProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <DialogTitle
    data-slot="sheet-title"
    :class="
      cn('text-foreground text-[length:var(--font-h2)] font-medium cn-font-heading', props.class)
    "
    v-bind="delegatedProps"
  >
    <slot />
  </DialogTitle>
</template>
