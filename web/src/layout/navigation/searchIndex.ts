import { routeIdentity } from './routeIdentity.ts'

/** No asset names are indexed. Parameterized details resolve to their safe list entry. */
export function searchIndex(isAdmin: boolean, translate: (key: string) => string, query = '') {
  const text = query.trim().toLocaleLowerCase()
  return Object.entries(routeIdentity)
    .filter(
      ([name, identity]) =>
        (!identity.adminOnly || isAdmin) &&
        ![
          'login',
          'register',
          'forgot-password',
          'reset-password',
          'forbidden',
          'not-found',
        ].includes(name),
    )
    .map(([name, identity]) => ({
      key: name,
      routeName: identity.object ? identity.owner : name,
      label: translate(identity.title),
      terms: [name, identity.title, ...(identity.aliases ?? []).map(translate)].join(' '),
    }))
    .filter((entry) => !text || `${entry.label} ${entry.terms}`.toLocaleLowerCase().includes(text))
}
