<script setup lang="ts">
import { NButton, NSpace } from 'naive-ui'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { GraphView } from '@/api/graph'

import { graphPaths, resolveLayout } from './graphLayout'

const props = defineProps<{
  graph: GraphView
  neighborhood: boolean
  layoutId?: string | null
  /** 质量叠加（G-28）：被隔离/违规命中的实体 IRI，节点叠加红色标记。 */
  flaggedIris?: Set<string>
  /** G-12 路径查询结果高亮。 */
  highlightIris?: Set<string>
}>()
const emit = defineEmits<{ select: [iri: string] }>()
const { t } = useI18n()
const zoom = ref(1)
const shortName = (iri: string) => iri.split(/[/#]/).filter(Boolean).at(-1) || iri
const layout = computed(() =>
  resolveLayout(props.layoutId, props.neighborhood).compute(props.graph),
)
const paths = computed(() =>
  graphPaths(layout.value.nodes, props.graph.edges, layout.value.edgePaths),
)
const isSchema = computed(() => props.layoutId === 'schema')
const edgeLabel = (edge: { props?: Record<string, unknown> | null; kind: string }) => {
  if (!edge.props) return ''
  const short = (value: unknown) => {
    const text = String(value)
    return /^https?:\/\//.test(text) ? shortName(text) || text : text
  }
  const parts = Object.entries(edge.props)
    .filter(([key]) => key !== '__typeCount__')
    .map(([key, value]) => `${key}=${short(value)}`)
  return parts.slice(0, 2).join(' ')
}
const nodeFlagged = (iri: string) => props.flaggedIris?.has(iri) ?? false
const nodeHighlighted = (iri: string) => props.highlightIris?.has(iri) ?? false
const nodeBadgeText = (node: GraphView['nodes'][number]) => {
  const count = node.attrs.__typeCount__
  return typeof count === 'number' ? t('graph.entityCount', { count }) : ''
}
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
      <span v-if="flaggedIris?.size" class="legend flagged">{{ t('graph.qualityOverlay') }}</span>
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
        <g v-for="edge in paths" :key="edge.key" class="edge-group">
          <path
            v-if="edge.path"
            :d="edge.path"
            class="edge"
            :class="{ derived: edge.kind === 'DERIVED' }"
            :marker-end="
              edge.kind === 'DERIVED' ? 'url(#graph-derived-arrow)' : 'url(#graph-direct-arrow)'
            "
          >
            <title>
              {{
                t('graph.factDescription', {
                  subject: edge.subject,
                  predicate: edge.predicate,
                  object: edge.object_,
                })
              }}
            </title>
          </path>
          <text
            v-if="edge.path && edgeLabel(edge)"
            :x="edge.label?.x"
            :y="(edge.label?.y ?? 0) - 4"
            text-anchor="middle"
            class="edge-props"
            :class="{ derived: edge.kind === 'DERIVED' }"
          >
            {{ edgeLabel(edge) }}
          </text>
        </g>
        <g
          v-for="node in layout.nodes"
          :key="node.iri"
          :transform="`translate(${node.x},${node.y})`"
          class="node"
          :class="{
            center: neighborhood && node.distance === 0,
            highlighted: nodeHighlighted(node.iri),
          }"
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
            {{ isSchema ? nodeBadgeText(node) : shortName(node.type_iri).slice(0, 22) }}
          </text>
          <circle
            v-if="nodeFlagged(node.iri)"
            cx="70"
            cy="-18"
            r="8"
            class="quality-flag"
            role="img"
            :aria-label="t('graph.qualityFlagged')"
          >
            <title>{{ t('graph.qualityFlagged') }}</title>
          </circle>
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
.legend.flagged::before {
  border-top: 2px dotted var(--danger, #d03050);
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
.edge-props {
  fill: var(--text-secondary);
  font-size: 11px;
  paint-order: stroke;
  stroke: var(--bg-subtle);
  stroke-width: 3px;
}
.edge-props.derived {
  fill: var(--graph-derived);
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
.quality-flag {
  fill: var(--danger, #d03050);
}
.node.highlighted rect {
  stroke: var(--info, #2080f0);
  stroke-width: 3;
}
.group-label {
  fill: var(--text-secondary);
  font-size: 15px;
  font-weight: 600;
}
</style>
