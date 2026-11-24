<script setup lang="ts">
import { computed } from 'vue'

import { Button } from './primitives/button'
import { useControlField } from './useControlField'

const props = withDefaults(
  defineProps<{
    type?: 'default' | 'primary' | 'success' | 'info' | 'warning' | 'error'
    variant?: 'default' | 'outline' | 'secondary' | 'ghost' | 'destructive' | 'link'
    size?: 'tiny' | 'small' | 'medium' | 'large'
    attrType?: 'button' | 'submit' | 'reset'
    disabled?: boolean
    loading?: boolean
    block?: boolean
    text?: boolean
    tertiary?: boolean
    quaternary?: boolean
    secondary?: boolean
    circle?: boolean
  }>(),
  { attrType: 'button', size: 'medium' },
)
const { disabled } = useControlField(props)
const variant = computed(
  () =>
    props.variant ||
    (props.text
      ? 'link'
      : props.quaternary || props.tertiary
        ? 'ghost'
        : props.type === 'error'
          ? 'destructive'
          : props.type === 'primary'
            ? 'default'
            : props.secondary
              ? 'secondary'
              : 'outline'),
)
const buttonSize = computed(() =>
  props.circle
    ? 'icon'
    : props.size === 'large'
      ? 'lg'
      : props.size === 'tiny'
        ? 'xs'
        : props.size === 'small'
          ? 'sm'
          : 'default',
)
</script>
<template>
  <Button
    :type="attrType"
    :variant="variant"
    :size="buttonSize"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
    class="ui-button"
    :class="{ 'w-full': block, 'text-primary': type === 'primary' && (quaternary || text) }"
    :data-size="size"
  >
    <span v-if="loading" class="ui-spinner" aria-hidden="true" />
    <slot name="icon" /><slot />
  </Button>
</template>
