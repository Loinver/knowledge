<script setup lang="ts">
defineProps<{ title?: string }>()
</script>
<template>
  <fieldset class="ui-form-section">
    <legend v-if="title">{{ title }}</legend>
    <slot />
  </fieldset>
</template>
