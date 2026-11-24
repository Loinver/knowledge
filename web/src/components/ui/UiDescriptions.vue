<script setup lang="ts">
withDefaults(
  defineProps<{ column?: number; bordered?: boolean; title?: string; size?: string }>(),
  { column: 1 },
)
</script>
<template>
  <section>
    <h3 v-if="title">{{ title }}</h3>
    <dl
      class="ui-descriptions"
      :style="{ gridTemplateColumns: 'repeat(' + column + ', minmax(0,1fr))' }"
    >
      <slot />
    </dl>
  </section>
</template>
