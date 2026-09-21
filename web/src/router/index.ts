import type { RouteRecordRaw } from 'vue-router'
import { createRouter, createWebHistory } from 'vue-router'

import Dashboard from '@/views/Dashboard.vue'
import DataCatalog from '@/views/DataCatalog.vue'
import DataSources from '@/views/DataSources.vue'
import Designer from '@/views/Designer.vue'
import Domains from '@/views/Domains.vue'
import EntityDetail from '@/views/EntityDetail.vue'
import EntityTypes from '@/views/EntityTypes.vue'
import ExtractionRuns from '@/views/ExtractionRuns.vue'
import GovernanceRules from '@/views/GovernanceRules.vue'
import GraphBrowse from '@/views/GraphBrowse.vue'
import GraphEntities from '@/views/GraphEntities.vue'
import GraphEntityDetail from '@/views/GraphEntityDetail.vue'
import GraphEvidence from '@/views/GraphEvidence.vue'
import GraphReports from '@/views/GraphReports.vue'
import MappingWizard from '@/views/MappingWizard.vue'
import NotFound from '@/views/NotFound.vue'
import RelationTypes from '@/views/RelationTypes.vue'
import SamplePreview from '@/views/SamplePreview.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', name: 'dashboard', component: Dashboard, meta: { menu: 'dashboard' } },
  { path: '/ontology', redirect: '/ontology/entity-types', name: 'ontology-root' },
  { path: '/ontology/entity-types', name: 'entity-types', component: EntityTypes, meta: { menu: 'ontology' } },
  { path: '/ontology/entity-types/:id', name: 'entity-detail', component: EntityDetail, meta: { menu: 'ontology' } },
  { path: '/ontology/relation-types', name: 'relation-types', component: RelationTypes, meta: { menu: 'ontology' } },
  { path: '/ontology/domains', name: 'domains', component: Domains, meta: { menu: 'ontology' } },
  { path: '/ontology/designer', name: 'designer', component: Designer, meta: { menu: 'ontology' } },
  { path: '/datasources', name: 'datasources', component: DataSources, meta: { menu: 'datasources' } },
  { path: '/datasources/catalog', name: 'data-catalog', component: DataCatalog, meta: { menu: 'datasources' } },
  { path: '/datasources/preview', name: 'sample-preview', component: SamplePreview, meta: { menu: 'datasources' } },
  { path: '/extraction', name: 'mapping-wizard', component: MappingWizard, meta: { menu: 'extraction' } },
  { path: '/extraction/runs', name: 'extraction-runs', component: ExtractionRuns, meta: { menu: 'extraction' } },
  { path: '/graph', name: 'graph-browse', component: GraphBrowse, meta: { menu: 'graph' } },
  { path: '/graph/entities', name: 'graph-entities', component: GraphEntities, meta: { menu: 'graph' } },
  { path: '/graph/entities/:id', name: 'graph-entity-detail', component: GraphEntityDetail, meta: { menu: 'graph' } },
  { path: '/graph/evidence', name: 'graph-evidence', component: GraphEvidence, meta: { menu: 'graph' } },
  { path: '/graph/reports', name: 'graph-reports', component: GraphReports, meta: { menu: 'graph' } },
  { path: '/governance/rules', name: 'governance-rules', component: GovernanceRules, meta: { menu: 'governance' } },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFound },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
