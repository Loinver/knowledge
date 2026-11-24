<script setup lang="ts">
import type { CSSProperties } from 'vue'

import { Card, CardContent, CardHeader, CardTitle } from './primitives/card'
withDefaults(
  defineProps<{
    title?: string
    size?: string
    bordered?: boolean
    contentStyle?: string | CSSProperties
  }>(),
  { bordered: true },
)
</script>
<template>
  <Card class="ui-card gap-0 p-4" :style="{ borderColor: bordered ? undefined : 'transparent' }">
    <CardHeader v-if="title || $slots.header || $slots['header-extra']" class="ui-card-header p-0">
      <CardTitle class="ui-card-title"
        ><slot name="header">{{ title }}</slot></CardTitle
      ><slot name="header-extra" />
    </CardHeader>
    <CardContent class="p-0" :style="contentStyle"><slot /></CardContent><slot name="footer" />
  </Card>
</template>
