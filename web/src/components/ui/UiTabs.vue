<script setup lang="ts" generic="T extends SelectionKey = SelectionKey">
import { TabsList, TabsRoot, TabsTrigger } from 'reka-ui'
import type { VNode, VNodeChild } from 'vue'
import { computed, Fragment, provide, ref, useSlots } from 'vue'

import type { SelectionKey } from './selectionTypes'
import { selectionKey, tabsContextKey } from './selectionTypes'
import { useControlField } from './useControlField'

const props = defineProps<{
  value?: T
  defaultValue?: T
  disabled?: boolean
  readonly?: boolean
  type?: string
  size?: string
  animated?: boolean
  placement?: string
}>()
const emit = defineEmits<{ 'update:value': [value: T]; change: [value: T] }>()
const slots = useSlots()
const { field, disabled, readonly, attributes } = useControlField(props)
const local = ref(props.defaultValue)
function flatten(nodes: VNode[]): VNode[] {
  return nodes.flatMap((node) =>
    node.type === Fragment && Array.isArray(node.children)
      ? flatten(node.children as VNode[])
      : [node],
  )
}
const panes = computed(() =>
  flatten(slots.default?.() ?? []).filter((node) => node.props?.name !== undefined),
)
const value = computed(
  () => props.value ?? local.value ?? (panes.value[0]?.props?.name as SelectionKey | undefined),
)
provide(tabsContextKey, { value })
function update(encoded: string | number) {
  const next = panes.value.find((pane) => selectionKey(pane.props!.name) === encoded)?.props
    ?.name as T | undefined
  if (next === undefined || disabled.value || readonly.value || next === value.value) return
  local.value = next
  emit('update:value', next)
  emit('change', next)
  field?.validate('input')
}
const Label = (labelProps: { pane: VNode }): VNodeChild => {
  const children = labelProps.pane.children
  const tabSlot =
    children && typeof children === 'object' && !Array.isArray(children) ? children.tab : undefined
  const tab = labelProps.pane.props?.tab
  return typeof tabSlot === 'function'
    ? tabSlot()
    : typeof tab === 'function'
      ? tab()
      : (tab as VNodeChild)
}
</script>
<template>
  <TabsRoot
    v-bind="$attrs"
    :model-value="value === undefined ? undefined : selectionKey(value)"
    :unmount-on-hide="true"
    :orientation="placement === 'left' || placement === 'right' ? 'vertical' : 'horizontal'"
    @update:model-value="update"
    @focusout="field?.validate('blur')"
  >
    <TabsList v-bind="attributes" class="ui-tabs-list"
      ><TabsTrigger
        v-for="tabPane in panes"
        :key="selectionKey(tabPane.props!.name)"
        class="ui-tab"
        :value="selectionKey(tabPane.props!.name)"
        :disabled="disabled || readonly || tabPane.props?.disabled"
        ><Label :pane="tabPane" /></TabsTrigger
      ><slot name="suffix"
    /></TabsList>
    <slot />
  </TabsRoot>
</template>
