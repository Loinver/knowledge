<script setup lang="ts">
import { NButton, NSpace } from 'naive-ui'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { GraphView } from '@/api/graph'
import { graphPaths, layoutGraph } from '@/components/graphLayout'

const props = defineProps<{ graph: GraphView; neighborhood: boolean }>()
const emit = defineEmits<{ select: [iri: string] }>()
const { t } = useI18n()
const zoom = ref(1)
const shortName = (iri: string) => iri.split(/[/#]/).filter(Boolean).at(-1) || iri
const layout = computed(() => layoutGraph(props.graph.nodes, props.neighborhood))
const paths = computed(() => graphPaths(layout.value.nodes, props.graph.edges))

</script>

<template>
  <div class="canvas-panel">
    <NSpace align="center">
      <NButton
        :disabled="zoom <= 0.4"
        :aria-label="t('graph.zoomOut')"
        @click="zoom = Math.max(0.4, zoom - 0.2)"
        >{{ t('graph.zoomOut') }}</NButton
      >
      <NButton
        :disabled="zoom >= 2"
        :aria-label="t('graph.zoomIn')"
        @click="zoom = Math.min(2, zoom + 0.2)"
        >{{ t('graph.zoomIn') }}</NButton
      >
      <NButton @click="zoom = 1">{{ t('graph.resetZoom') }}</NButton>
      <span class="legend direct">{{ t('graph.directRelation') }}</span>
      <span class="legend derived">{{ t('graph.derived') }}</span>
    </NSpace>
    <p class="hint">{{ t('graph.canvasHint') }}</p>
    <div class="canvas-scroll" tabindex="0" :aria-label="t('page.graphBrowse')">
      <svg
        :width="layout.width * zoom"
        :height="layout.height * zoom"
        :viewBox="`0 0 ${layout.width} ${layout.height}`"
        role="group"
        :aria-label="t('page.graphBrowse')"
      >
        <defs>
          <marker
            id="graph-direct-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" class="arrow-direct" />
          </marker>
          <marker
            id="graph-derived-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" class="arrow-derived" />
          </marker>
        </defs>
        <text
          v-for="group in layout.groups"
          :key="group.type"
          x="35"
          :y="group.y"
          class="group-label"
        >
          {{ shortName(group.type) }}
        </text>
        <path
          v-for="edge in paths"
          :key="edge.key"
          :d="edge.path"
          class="edge"
          :class="{ derived: edge.kind === 'DERIVED' }"
          :marker-end="
            edge.kind === 'DERIVED' ? 'url(#graph-derived-arrow)' : 'url(#graph-direct-arrow)'
          "
        >
          <title>{{ t('graph.factDescription', { subject: edge.subject, predicate: edge.predicate, object: edge.object_ }) }}</title>
        </path>
        <g
          v-for="node in layout.nodes"
          :key="node.iri"
          :transform="`translate(${node.x},${node.y})`"
          class="node"
          :class="{ center: neighborhood && node.distance === 0 }"
          tabindex="0"
          role="button"
          :aria-label="t('graph.exploreEntity', { iri: node.iri })"
          @click="emit('select', node.iri)"
          @keydown.enter.prevent="emit('select', node.iri)"
          @keydown.space.prevent="emit('select', node.iri)"
        >
          <title>{{ node.iri }}</title>
          <rect x="-80" y="-26" width="160" height="52" rx="8" />
          <text y="-3" text-anchor="middle">
            {{ String(node.attrs.name ?? node.row_key).slice(0, 18) }}
          </text>
          <text y="16" text-anchor="middle" class="node-type">
            {{ shortName(node.type_iri).slice(0, 22) }}
          </text>
        </g>
      </svg>
    </div>
  </div>
</template>

<style scoped>
.canvas-panel {
  display: grid;
  gap: 12px;
  min-width: 0;
}
.canvas-scroll {
  overflow: auto;
  max-height: 600px;
  border: 1px solid var(--border);
  background: var(--bg-subtle);
  border-radius: var(--radius-large);
}
.hint {
  margin: 0;
  color: var(--text-secondary);
}
.legend {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.legend::before {
  content: '';
  width: 30px;
  border-top: 2px solid var(--text-secondary);
}
.legend.derived::before {
  border-top: 2px dashed var(--graph-derived);
}
.edge {
  fill: none;
  stroke: var(--text-secondary);
  stroke-width: 1.5;
}
.edge.derived {
  stroke: var(--graph-derived);
  stroke-dasharray: 7 5;
}
.arrow-direct {
  fill: var(--text-secondary);
}
.arrow-derived {
  fill: var(--graph-derived);
}
.node {
  cursor: pointer;
}
.node rect {
  fill: var(--bg);
  stroke: var(--border-strong);
  stroke-width: 1.5;
}
.node:hover rect,
.node:focus rect,
.node.center rect {
  stroke: var(--pri);
  stroke-width: 3;
}
.node text {
  fill: var(--text);
  font-size: 13px;
  pointer-events: none;
}
.node .node-type {
  fill: var(--text-secondary);
  font-size: 11px;
}
.group-label {
  fill: var(--text-secondary);
  font-size: 15px;
  font-weight: 600;
}
</style>
