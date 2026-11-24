<script setup lang="ts">
defineOptions({ inheritAttrs: false })
defineProps<{ size?: string; bordered?: boolean; singleLine?: boolean }>()
</script>
<template>
  <div class="ui-table-scroll">
    <table v-bind="$attrs" class="ui-table">
      <slot />
    </table>
  </div>
</template>
