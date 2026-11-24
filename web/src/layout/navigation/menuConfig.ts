import type { IconName } from '@/components/icons'

export interface MenuNode {
  key: string
  labelKey: string
  icon?: IconName
  adminOnly?: boolean
  children?: MenuNode[]
}

export const GROUP_PREFIX = 'group:'

/** Production navigation. Groups expand; only leaves identify a route. */
export const menuConfig: MenuNode[] = [
  { key: 'dashboard', labelKey: 'page.dashboard', icon: 'dashboard' },
  {
    key: 'group:semantic-assets',
    labelKey: 'menu.semanticAssets',
    icon: 'ontology',
    children: [
      { key: 'namespaces', labelKey: 'page.namespaces' },
      { key: 'entity-types', labelKey: 'page.entityTypes' },
      { key: 'relation-types', labelKey: 'page.relationTypes' },
      { key: 'domains', labelKey: 'page.domains' },
      {
        key: 'group:configuration',
        labelKey: 'menu.assetConfiguration',
        children: [
          { key: 'enum-dictionaries', labelKey: 'enumDictionaries.title' },
          { key: 'assembly-templates', labelKey: 'templates.title' },
        ],
      },
    ],
  },
  {
    key: 'group:ontology',
    labelKey: 'menu.ontologyAssembly',
    icon: 'ontology',
    children: [
      { key: 'ontologies', labelKey: 'page.ontologies' },
      { key: 'designer', labelKey: 'page.designer' },
      { key: 'graph-reports', labelKey: 'page.graphReports' },
    ],
  },
  {
    key: 'group:data-integration',
    labelKey: 'menu.dataIntegration',
    icon: 'datasource',
    children: [
      { key: 'datasources', labelKey: 'page.dataSources' },
      { key: 'data-catalog', labelKey: 'page.dataCatalog' },
      { key: 'mapping-wizard', labelKey: 'page.mappingWizard' },
      { key: 'extraction-tasks', labelKey: 'page.extractionTasks' },
      { key: 'extraction-runs', labelKey: 'page.extractionRuns' },
    ],
  },
  {
    key: 'group:graph',
    labelKey: 'menu.graph',
    icon: 'graph',
    children: [
      { key: 'graph-browse', labelKey: 'page.graphBrowse' },
      { key: 'graph-entities', labelKey: 'page.graphEntities' },
      { key: 'graph-evidence', labelKey: 'page.graphEvidence' },
    ],
  },
  {
    key: 'group:governance',
    labelKey: 'menu.standardsGovernance',
    icon: 'governance',
    children: [
      { key: 'governance-clauses', labelKey: 'page.governanceClauses' },
      { key: 'governance-rules', labelKey: 'page.governanceRules' },
      { key: 'ontology-export', labelKey: 'ui.exchange' },
    ],
  },
  { key: 'knowledge-bases', labelKey: 'kb.title', icon: 'datasource' },
  {
    key: 'group:system',
    labelKey: 'menu.system',
    icon: 'system',
    adminOnly: true,
    children: [
      { key: 'system-users', labelKey: 'page.systemUsers' },
      { key: 'system-roles', labelKey: 'page.systemRoles' },
      { key: 'system-audit-logs', labelKey: 'page.systemAuditLogs' },
      { key: 'system-ai-models', labelKey: 'page.systemAiModels' },
    ],
  },
]

export function visibleMenu(isAdmin: boolean, nodes = menuConfig): MenuNode[] {
  return nodes
    .filter((node) => !node.adminOnly || isAdmin)
    .map((node) => ({
      ...node,
      ...(node.children ? { children: visibleMenu(isAdmin, node.children) } : {}),
    }))
}

export function menuTrail(key: string, nodes = menuConfig): MenuNode[] {
  for (const node of nodes) {
    if (node.key === key) return [node]
    const child = node.children ? menuTrail(key, node.children) : []
    if (child.length) return [node, ...child]
  }
  return []
}

export function menuLeaves(nodes = menuConfig): MenuNode[] {
  return nodes.flatMap((node) => (node.children ? menuLeaves(node.children) : [node]))
}
