<script setup lang="ts">
defineProps<{ name: string; size?: number }>()
const paths: Record<string, string> = {
  dashboard: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  assets: 'm12 3 9 5-9 5-9-5 9-5z M3 12l9 5 9-5 M3 16l9 5 9-5',
  designer: 'M4 4h6v6H4z M14 14h6v6h-6z M7 10v7h7 M10 7h7v7',
  mapping: 'M4 4h6v5H4z M14 15h6v5h-6z M7 9v8h7 M14 4h6 M17 1v6',
  graph:
    'M7 5a2 2 0 1 0-4 0 2 2 0 0 0 4 0 M21 7a2 2 0 1 0-4 0 2 2 0 0 0 4 0 M14 19a2 2 0 1 0-4 0 2 2 0 0 0 4 0 M7 6l10 1 M6 7l5 10 M18 9l-5 8',
  governance: 'M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3z m-4 9 3 3 5-6',
  knowledge: 'M3 4h7l2 2 2-2h7v15h-7l-2 2-2-2H3V4z M12 6v15',
  system:
    'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2',
  search: 'M11 3a8 8 0 1 0 0 16 8 8 0 0 0 0-16 M17 17l5 5',
  close: 'M6 6l12 12 M18 6 6 18',
  arrow: 'M5 12h14 M14 7l5 5-5 5',
  down: 'm6 9 6 6 6-6',
  plus: 'M12 5v14 M5 12h14',
  minus: 'M5 12h14',
  check: 'm5 12 4 4L19 6',
  filter: 'M4 5h16 M7 12h10 M10 19h4',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M12 7v5l4 2',
  box: 'm12 3 9 5v9l-9 5-9-5V8l9-5z M3 8l9 5 9-5 M12 13v9',
  link: 'm10 13 4-4 M8 16l-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0 M13 17a4 4 0 0 0 6 0l4-4a4 4 0 0 0-6-6l-1 1',
  expand: 'M4 9V4h5 M15 4h5v5 M20 15v5h-5 M9 20H4v-5',
  panel: 'M3 4h18v16H3z M9 4v16',
  copy: 'M8 8h12v13H8z M16 8V3H3v13h5',
  warning: 'm12 3 10 17H2L12 3z M12 8v6 M12 17v1',
  file: 'M5 3h10l4 4v14H5V3z M14 3v5h5 M8 12h8 M8 16h5',
  dots: 'M5 12h.1 M12 12h.1 M19 12h.1',
  save: 'M4 3h14l3 3v15H3V3h1 M7 3v6h9V3 M7 21v-8h10v8',
}
</script>
<template>
  <svg
    :width="size || 18"
    :height="size || 18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[name] || paths.box" />
  </svg>
</template>
