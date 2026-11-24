import { menuLeaves, menuTrail } from './menuConfig.ts'

export interface RouteIdentity {
  title: string
  owner: string
  object?: boolean
  adminOnly?: boolean
  aliases?: string[]
}

/** Hidden details and tools have one owner; public/account pages have their own identity. */
export const routeIdentity: Record<string, RouteIdentity> = {
  ...Object.fromEntries(
    menuLeaves().map((leaf) => [
      leaf.key,
      {
        title: leaf.labelKey,
        owner: leaf.key,
        adminOnly: menuTrail(leaf.key).some((node) => node.adminOnly),
      },
    ]),
  ),
  'entity-detail': { title: 'page.entityDetail', owner: 'entity-types', object: true },
  'relation-detail': { title: 'page.relationDetail', owner: 'relation-types', object: true },
  'graph-entity-detail': { title: 'page.graphEntityDetail', owner: 'graph-entities', object: true },
  'knowledge-base-detail': { title: 'kb.detail', owner: 'knowledge-bases', object: true },
  'knowledge-base-search': { title: 'kb.searchTitle', owner: 'knowledge-bases', object: true },
  'sample-preview': { title: 'page.samplePreview', owner: 'data-catalog' },
  'ai-assist': { title: 'page.aiAssist', owner: 'mapping-wizard' },
  'account-profile': { title: 'account.profile', owner: 'account-profile' },
  'account-security': { title: 'account.security', owner: 'account-security' },
  login: { title: 'auth.login', owner: 'login' },
  register: { title: 'auth.registerTitle', owner: 'register' },
  'forgot-password': { title: 'auth.forgotTitle', owner: 'forgot-password' },
  'reset-password': { title: 'auth.resetTitle', owner: 'reset-password' },
  forbidden: { title: 'page.forbiddenTitle', owner: 'forbidden' },
  'not-found': { title: 'page.notFound', owner: 'not-found' },
}

routeIdentity['graph-reports'].aliases = ['navigation.validationReport']
routeIdentity['graph-evidence'].aliases = ['navigation.knowledgeTrace']

export function identityFor(name: unknown): RouteIdentity | undefined {
  return typeof name === 'string' ? routeIdentity[name] : undefined
}
