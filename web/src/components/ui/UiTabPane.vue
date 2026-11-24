<script setup lang="ts">
import { TabsContent } from 'reka-ui'
import type { VNodeChild } from 'vue'
import { computed, inject } from 'vue'

import type { SelectionKey } from './selectionTypes'
import { selectionKey, tabsContextKey } from './selectionTypes'
import { useControlField } from './useControlField'

const props = withDefaults(
  defineProps<{
    name: SelectionKey
    tab?: string | number | (() => VNodeChild)
    disabled?: boolean
    readonly?: boolean
    displayDirective?: 'if' | 'show' | 'show:lazy'
  }>(),
  { displayDirective: 'if' },
)
const context = inject(tabsContextKey, undefined)
const { field, attributes } = useControlField(props)
const active = computed(() => context?.value.value === props.name)
</script>
<template>
  <TabsContent
    v-show="active"
    class="ui-tabs-content"
    :value="selectionKey(name)"
    :aria-describedby="attributes['aria-describedby']"
    :aria-invalid="attributes['aria-invalid']"
    :force-mount="displayDirective === 'show'"
    @focusout="field?.validate('blur')"
    ><slot
  /></TabsContent>
</template>
