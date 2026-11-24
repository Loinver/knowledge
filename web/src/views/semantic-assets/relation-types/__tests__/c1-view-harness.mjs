import { mount as mountView } from '../../../../testing/view-harness.mjs'

export { deferred, settle } from '../../../../testing/view-harness.mjs'

// The shared harness's UI virtual namespace cannot resolve its absolute re-export.
// Resolve the identical UI index through its file entry for these script-level tests.
// Component rendering is tested separately with the actual SFC compiler.
export function mount(
  entry,
  stubs,
  expose,
  start = '/',
  transform = (source) => source,
  role = 'EDITOR',
) {
  return mountView(
    entry,
    stubs,
    expose,
    start,
    (source) =>
      transform(source).replaceAll("from '@/components/ui'", "from '@/components/ui/index'"),
    role,
  )
}
