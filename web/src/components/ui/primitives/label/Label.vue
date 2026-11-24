<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/label.json; original registry SHA256: f5fc8f62f50069c0f62bb83af04e0530aafb05d8c8852a3d03b289bdf6096aee. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'
import type { LabelProps } from 'reka-ui'
import { Label } from 'reka-ui'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<LabelProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <Label
    data-slot="label"
    v-bind="delegatedProps"
    :class="
      cn(
        'gap-2 text-[length:var(--font-body)] leading-none font-medium group-data-[disabled=true]:opacity-50 peer-disabled:opacity-50 flex items-center select-none group-data-[disabled=true]:pointer-events-none peer-disabled:cursor-not-allowed',
        props.class,
      )
    "
  >
    <slot />
  </Label>
</template>
