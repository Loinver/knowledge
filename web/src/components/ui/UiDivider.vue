<script setup lang="ts">
import { Separator } from './primitives/separator'
defineProps<{ vertical?: boolean }>()
</script>
<template><Separator :orientation="vertical ? 'vertical' : 'horizontal'" class="my-4" /></template>
