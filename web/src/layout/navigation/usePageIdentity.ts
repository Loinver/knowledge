import type { InjectionKey, Ref } from 'vue'
import { inject, onScopeDispose, provide, ref, watchEffect } from 'vue'
import { useRoute } from 'vue-router'

interface PageIdentity {
  path: string
  label: string
  owner: symbol
}
const identityKey: InjectionKey<Ref<PageIdentity | null>> = Symbol('page-identity')

export function providePageIdentity() {
  const identity = ref<PageIdentity | null>(null)
  provide(identityKey, identity)
  return identity
}

export function currentPageIdentity() {
  return inject(identityKey, ref<PageIdentity | null>(null))
}

/** A page publishes only the identity of data already loaded by its own guarded request. */
export function usePageIdentity(label: () => string | undefined | null) {
  const identity = inject(identityKey, null)
  const route = useRoute()
  const owner = Symbol('identity-owner')
  if (!identity) return
  watchEffect(() => {
    identity.value = { path: route.fullPath, label: label() ?? '', owner }
  })
  onScopeDispose(() => {
    if (identity.value?.owner === owner) identity.value = null
  })
}
