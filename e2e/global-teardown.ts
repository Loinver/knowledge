import { basename, resolve, sep } from 'node:path'
import { rmSync } from 'node:fs'
import { tmpdir } from 'node:os'

export default function globalTeardown(): void {
  const directory = process.env.KG_E2E_TEMP_DIR
  if (!directory) return

  const resolved = resolve(directory)
  const tmpRoot = resolve(tmpdir()) + sep
  if (!resolved.startsWith(tmpRoot) || !basename(resolved).startsWith('knowledge-e2e-')) {
    throw new Error('Refusing to remove an E2E path outside the generated temp directory')
  }
  rmSync(resolved, { recursive: true, force: true })
}
