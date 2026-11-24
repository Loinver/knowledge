<script setup lang="ts">
import type { MenuOption } from './menuTypes'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './primitives/dropdown-menu'
defineProps<{ options: MenuOption[]; trigger?: string }>()
const emit = defineEmits<{ select: [key: string | number] }>()
</script>
<template>
  <DropdownMenu
    ><DropdownMenuTrigger as-child><slot /></DropdownMenuTrigger>
    <DropdownMenuContent class="ui-popup z-[var(--z-popover)]" align="end">
      <template v-for="(option, index) in options" :key="option.key ?? index">
        <DropdownMenuSeparator v-if="option.type === 'divider'" />
        <DropdownMenuItem
          v-else-if="option.show !== false"
          :disabled="option.disabled"
          class="ui-option"
          @select="option.key !== undefined && emit('select', option.key)"
        >
          <component :is="option.icon" v-if="option.icon" /><component
            :is="option.label"
            v-if="typeof option.label === 'function'"
          /><template v-else>{{ option.label }}</template>
        </DropdownMenuItem>
      </template>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
