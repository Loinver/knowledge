import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

// 对应 .agents/conventions/security-and-license.md；未知或组合许可需单独核验。
const allowed = new Set([
  'MIT',
  'BSD-2-Clause',
  'BSD-3-Clause',
  'Apache-2.0',
  'ISC',
  'PSF-2.0',
  'Python-2.0',
])
const report = JSON.parse(
  execFileSync(
    'pnpm',
    ['--filter', '@knowledge/web', '--fail-if-no-match', 'licenses', 'list', '--prod', '--json'],
    {
      cwd: fileURLToPath(new URL('../', import.meta.url)),
      encoding: 'utf8',
      maxBuffer: 16 * 1024 * 1024,
    },
  ),
)

let total = 0
const violations = []
for (const [license, packages] of Object.entries(report)) {
  if (!Array.isArray(packages)) throw new Error('Invalid pnpm license report')
  total += packages.length
  if (!allowed.has(license)) {
    violations.push(...packages.map((pkg) => `${pkg.name}@${pkg.versions.join(', ')}: ${license}`))
  }
}
if (total === 0) throw new Error('No production packages were included in the license report')

if (violations.length) {
  console.error('Licenses outside the repository allowlist:\n' + violations.join('\n'))
  process.exitCode = 1
} else {
  console.log(`Web production licenses OK: ${total} packages`)
}
