<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/input-group.json; original registry SHA256: 128d4c1d4a279152f73826699d795b0faa34d308851c92a39b739a5504ebc3e5. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { Button } from '@/components/ui/primitives/button'
import { cn } from '@/components/ui/utils'

import type { InputGroupButtonProps } from '.'
import { inputGroupButtonVariants } from '.'

const props = withDefaults(defineProps<InputGroupButtonProps>(), {
  size: 'xs',
  variant: 'ghost',
})
</script>

<template>
  <Button
    type="button"
    :data-size="props.size"
    :variant="props.variant"
    :class="cn(inputGroupButtonVariants({ size: props.size }), props.class)"
  >
    <slot />
  </Button>
</template>
