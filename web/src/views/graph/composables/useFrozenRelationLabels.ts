import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { graphApi, viewTemplateApi } from '@/api/graph'
import { useAsyncData } from '@/composables/useAsyncData'
import { relationLabels } from '@/views/graph/components/graphPresentation'

/** Detail and trace responses identify a result set, but do not include its ontology pin. */
export function useFrozenRelationLabels(
  graphRevision: () => number | undefined,
  predicates: () => readonly string[],
) {
  const { t, locale } = useI18n()
  const request = useAsyncData(async (signal) => {
    const revision = graphRevision()
    if (!revision) return null
    const graph = await graphApi.view(
      { graph_revision_id: revision, node_limit: 1, edge_limit: 1 },
      signal,
    )
    if (signal.aborted) return null
    if (graph?.graph_revision_id !== revision || !graph.ontology_id || !graph.ontology_revision)
      throw { code: 'KG.RESOURCE_NOT_FOUND' }
    const catalog = await viewTemplateApi.fields(graph.ontology_id, graph.ontology_revision, signal)
    if (
      catalog.ontology_id !== graph.ontology_id ||
      catalog.ontology_revision !== graph.ontology_revision
    )
      throw { code: 'KG.RESOURCE_NOT_FOUND' }
    return { revision, graph, catalog }
  })
  const labels = computed(() => {
    const current = request.data.value
    const untranslated = t('enumDictionaries.untranslated')
    const edges = predicates().map((predicate) => ({ predicate }))
    const resolved = relationLabels(
      current && current.revision === graphRevision() ? { ...current.graph, edges } : null,
      current?.catalog ?? null,
      locale.value,
      untranslated,
    )
    // Keep the raw identifier visible while loading, on failure, and for unknown aliases.
    for (const { predicate } of edges) resolved[predicate] ??= `${predicate} · ${untranslated}`
    return resolved
  })
  const name = (predicate: string) =>
    labels.value[predicate] ?? `${predicate} · ${t('enumDictionaries.untranslated')}`
  return { labels, name, error: request.error, loading: request.loading, reload: request.reload }
}
