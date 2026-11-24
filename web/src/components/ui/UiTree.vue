<script setup lang="ts">
import { ChevronDown, ChevronRight } from '@lucide/vue'
import type { TreeItemSelectEvent } from 'reka-ui'
import { TreeItem, TreeRoot } from 'reka-ui'
import type { VNodeChild } from 'vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import Checkbox from './primitives/checkbox/Checkbox.vue'
import type { SelectionKey, TreeOption, TreeSelectMeta } from './selectionTypes'
import { sameSelection, selectionKey } from './selectionTypes'
import { useControlField } from './useControlField'

const props = withDefaults(
  defineProps<{
    data?: TreeOption[]
    keyField?: string
    labelField?: string
    childrenField?: string
    selectedKeys?: SelectionKey[]
    expandedKeys?: SelectionKey[]
    checkedKeys?: SelectionKey[]
    defaultSelectedKeys?: SelectionKey[]
    defaultExpandedKeys?: SelectionKey[]
    defaultCheckedKeys?: SelectionKey[]
    defaultExpandAll?: boolean
    selectable?: boolean
    multiple?: boolean
    checkable?: boolean
    cascade?: boolean
    disabled?: boolean
    readonly?: boolean
    blockLine?: boolean
    blockNode?: boolean
    renderLabel?: (info: { option: TreeOption; checked: boolean; selected: boolean }) => VNodeChild
  }>(),
  { keyField: 'key', labelField: 'label', childrenField: 'children', selectable: true },
)
const emit = defineEmits<{
  'update:selectedKeys': [keys: SelectionKey[], options: TreeOption[], meta: TreeSelectMeta]
  'update:expandedKeys': [
    keys: SelectionKey[],
    options: TreeOption[],
    meta: { node: TreeOption | null; action: 'expand' | 'collapse' },
  ]
  'update:checkedKeys': [keys: SelectionKey[], options: TreeOption[], meta: TreeSelectMeta]
}>()
const { t } = useI18n()
const { field, disabled, readonly, attributes } = useControlField(props)
const selectedLocal = ref(props.defaultSelectedKeys ?? [])
const expandedLocal = ref(props.defaultExpandedKeys ?? [])
const checkedLocal = ref(props.defaultCheckedKeys ?? [])
const selected = computed(() => props.selectedKeys ?? selectedLocal.value)
const expanded = computed(() => props.expandedKeys ?? expandedLocal.value)
const checked = computed(() => props.checkedKeys ?? checkedLocal.value)
const nodeKey = (node: TreeOption): SelectionKey => node[props.keyField] as SelectionKey
const getKey = (node: TreeOption) => selectionKey(nodeKey(node))
function children(node: TreeOption): TreeOption[] | undefined {
  const values = node[props.childrenField] as TreeOption[] | undefined
  return values?.length ? values : undefined
}
const nodes = computed(() => {
  const result = new Map<string, TreeOption>()
  const visit = (data: TreeOption[]) =>
    data.forEach((node) => {
      result.set(getKey(node), node)
      visit(children(node) ?? [])
    })
  visit(props.data ?? [])
  return result
})
const optionForKeys = (keys: SelectionKey[]) =>
  keys
    .map((key) => nodes.value.get(selectionKey(key)))
    .filter((node): node is TreeOption => Boolean(node))
const model = computed(() => optionForKeys(selected.value))
const expandedModel = computed(() => expanded.value.map(selectionKey))
const seenNodes = new Set<string>()
watch(
  nodes,
  () => {
    if (
      props.defaultExpandAll &&
      props.expandedKeys === undefined &&
      props.defaultExpandedKeys === undefined
    ) {
      expandedLocal.value = [
        ...new Set([
          ...expandedLocal.value,
          ...[...nodes.value.values()]
            .filter((node) => children(node) && !seenNodes.has(getKey(node)))
            .map(nodeKey),
        ]),
      ]
    }
    for (const key of nodes.value.keys()) seenNodes.add(key)
  },
  { immediate: true },
)
function select(event: TreeItemSelectEvent<TreeOption>) {
  event.preventDefault()
  const node = event.detail.value
  if (!node || !props.selectable || disabled.value || readonly.value || node.disabled) return
  const key = nodeKey(node)
  const remove = props.multiple && selected.value.includes(key)
  const next = props.multiple
    ? remove
      ? selected.value.filter((value) => value !== key)
      : [...selected.value, key]
    : [key]
  if (sameSelection(selected.value, next)) return
  selectedLocal.value = next
  emit('update:selectedKeys', next, optionForKeys(next), {
    node,
    action: remove ? 'unselect' : 'select',
  })
  field?.validate('input')
}
function updateSelection(values: unknown) {
  if (disabled.value || readonly.value || !props.selectable) return
  const options = (Array.isArray(values) ? values : values ? [values] : []) as TreeOption[]
  const available = options.filter((node) => !node.disabled)
  const next = (props.multiple ? available : available.slice(-1)).map(nodeKey)
  if (sameSelection(selected.value, next)) return
  const node = available.at(-1) ?? null
  selectedLocal.value = next
  emit('update:selectedKeys', next, optionForKeys(next), {
    node,
    action: next.length ? 'select' : 'unselect',
  })
  field?.validate('input')
}
function expand(encoded: string[]) {
  if (disabled.value || readonly.value) return
  const next = encoded
    .map((key) => nodes.value.get(key))
    .filter((node): node is TreeOption => Boolean(node))
    .map(nodeKey)
  if (sameSelection(expanded.value, next)) return
  const added = next.find((key) => !expanded.value.includes(key))
  const changed = added ?? expanded.value.find((key) => !next.includes(key))
  expandedLocal.value = next
  emit('update:expandedKeys', next, optionForKeys(next), {
    node: changed === undefined ? null : (nodes.value.get(selectionKey(changed)) ?? null),
    action: added === undefined ? 'collapse' : 'expand',
  })
  field?.validate('input')
}
function check(node: TreeOption, value: boolean | 'indeterminate') {
  if (
    disabled.value ||
    readonly.value ||
    node.disabled ||
    node.checkboxDisabled ||
    value === 'indeterminate'
  )
    return
  const keys = new Set(checked.value)
  const visit = (item: TreeOption) => {
    if (item.disabled || item.checkboxDisabled) return
    if (value) keys.add(nodeKey(item))
    else keys.delete(nodeKey(item))
    if (props.cascade) (children(item) ?? []).forEach(visit)
  }
  visit(node)
  if (props.cascade) {
    const parents = [...nodes.value.values()].reverse()
    for (const parent of parents) {
      const childNodes = children(parent)?.filter(
        (child) => !child.disabled && !child.checkboxDisabled,
      )
      if (!childNodes?.length || parent.disabled || parent.checkboxDisabled) continue
      if (childNodes.every((child) => keys.has(nodeKey(child)))) keys.add(nodeKey(parent))
      else keys.delete(nodeKey(parent))
    }
  }
  const next = [...keys]
  if (sameSelection(checked.value, next)) return
  checkedLocal.value = next
  emit('update:checkedKeys', next, optionForKeys(next), {
    node,
    action: value ? 'check' : 'uncheck',
  })
  field?.validate('input')
}
function indeterminate(node: TreeOption): boolean {
  return Boolean(
    props.cascade &&
    !checked.value.includes(nodeKey(node)) &&
    children(node)?.some((child) => checked.value.includes(nodeKey(child)) || indeterminate(child)),
  )
}
const Label = (labelProps: { node: TreeOption }): VNodeChild => {
  const node = labelProps.node
  const label = node[props.labelField]
  return (
    props.renderLabel?.({
      option: node,
      checked: checked.value.includes(nodeKey(node)),
      selected: selected.value.includes(nodeKey(node)),
    }) ?? (typeof label === 'function' ? label() : (label as VNodeChild))
  )
}
const Render = (renderProps: { render: () => VNodeChild }): VNodeChild => renderProps.render()
</script>
<template>
  <TreeRoot
    v-slot="{ flattenItems }"
    v-bind="{ ...$attrs, ...attributes, 'aria-readonly': readonly || undefined }"
    :items="data ?? []"
    :get-key="getKey"
    :get-children="children"
    :model-value="multiple ? model : model[0]"
    :multiple="multiple"
    :expanded="expandedModel"
    :disabled="disabled || readonly"
    @update:expanded="expand"
    @update:model-value="updateSelection"
    @focusout="field?.validate('blur')"
  >
    <TreeItem
      v-for="item in flattenItems"
      :key="item._id"
      v-slot="{ isExpanded, handleToggle }"
      v-bind="item.bind"
      class="ui-tree-item"
      :style="{ paddingInlineStart: `calc(var(--space-4) * ${item.level - 1} + var(--space-2))` }"
      :disabled="item.value.disabled"
      @select="select"
      @toggle="readonly && $event.preventDefault()"
    >
      <button
        v-if="item.hasChildren"
        class="tree-toggle"
        type="button"
        tabindex="-1"
        :disabled="disabled || readonly || item.value.disabled"
        :aria-label="t(isExpanded ? 'ds.collapse' : 'ds.expand')"
        @click.stop="handleToggle"
      >
        <ChevronDown v-if="isExpanded" :size="16" /><ChevronRight v-else :size="16" /></button
      ><span v-else class="tree-spacer" />
      <Checkbox
        v-if="checkable"
        :model-value="
          indeterminate(item.value) ? 'indeterminate' : checked.includes(nodeKey(item.value))
        "
        :disabled="disabled || readonly || item.value.disabled || item.value.checkboxDisabled"
        :aria-label="
          typeof item.value[labelField] === 'string'
            ? (item.value[labelField] as string)
            : t('ds.selectItem')
        "
        @click.stop
        @update:model-value="check(item.value, $event)"
      />
      <Render v-if="item.value.prefix" :render="item.value.prefix" /><Label
        :node="item.value"
      /><span v-if="item.value.suffix" class="tree-suffix"
        ><Render :render="item.value.suffix"
      /></span>
    </TreeItem>
  </TreeRoot>
</template>
<style scoped>
.tree-toggle {
  display: flex;
  flex: none;
  border: 0;
  padding: 0;
  background: transparent;
  color: var(--foreground-muted);
}
.tree-spacer {
  width: var(--space-4);
  flex: none;
}
.tree-suffix {
  margin-inline-start: auto;
  font-size: var(--font-caption);
  color: var(--foreground-muted);
}
.ui-tree-item[aria-disabled='true'] {
  color: var(--foreground-disabled);
}
</style>
