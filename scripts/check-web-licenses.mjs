import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
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
const lightningPackages = new Set([
  'lightningcss',
  'lightningcss-darwin-x64',
  'lightningcss-linux-x64-gnu',
  'lightningcss-win32-x64-msvc',
  'lightningcss-win32-arm64-msvc',
  'lightningcss-darwin-arm64',
  'lightningcss-linux-arm64-gnu',
  'lightningcss-linux-arm-gnueabihf',
  'lightningcss-linux-arm64-musl',
  'lightningcss-linux-x64-musl',
  'lightningcss-freebsd-x64',
  'lightningcss-android-arm64',
])
export function isAllowedLicense(license, pkg, { scope = 'production' } = {}) {
  if (allowed.has(license)) return true
  // 2026-11-23: user approved this exact Tailwind build dependency family.
  // The production gate still rejects MPL. Names come from the installed
  // lightningcss@1.33.0 optionalDependencies, not an open package-name prefix.
  if (license === 'MPL-2.0') {
    return (
      scope === 'development' &&
      lightningPackages.has(pkg?.name) &&
      Array.isArray(pkg.versions) &&
      pkg.versions.length > 0 &&
      pkg.versions.every((version) => version === '1.33.0')
    )
  }
  // 2026-11-23 task approval: “批准本次 tslib@2.8.1 的 0BSD 例外”.
  // Exact package/version/license only; 0BSD remains outside the general allowlist.
  if (license === '0BSD') {
    return (
      pkg?.name === 'tslib' &&
      Array.isArray(pkg.versions) &&
      pkg.versions.length > 0 &&
      pkg.versions.every((version) => version === '2.8.1')
    )
  }
  // Task-scoped MIT selection; do not admit CC0 alone or unreviewed OR expressions.
  // Full upstream MIT and CC0 notices are retained in ui/THIRD_PARTY_LICENSES.md.
  return (
    license === '(MIT OR CC0-1.0)' &&
    pkg.name === 'type-fest' &&
    Array.isArray(pkg.versions) &&
    pkg.versions.length > 0 &&
    pkg.versions.every((version) => version === '4.41.0')
  )
}

export function validateLicenseReport(report, options = {}) {
  if (!report || typeof report !== 'object' || Array.isArray(report)) {
    throw new Error('Invalid pnpm license report')
  }
  let total = 0
  const violations = []
  for (const [license, packages] of Object.entries(report)) {
    if (!Array.isArray(packages)) throw new Error('Invalid pnpm license report')
    for (const pkg of packages) {
      if (
        !pkg ||
        typeof pkg.name !== 'string' ||
        !Array.isArray(pkg.versions) ||
        !pkg.versions.length ||
        pkg.versions.some((version) => typeof version !== 'string' || !version)
      ) {
        throw new Error('Invalid pnpm license report')
      }
      total += 1
      if (!isAllowedLicense(license, pkg, options)) {
        violations.push(`${pkg.name}@${pkg.versions.join(', ')}: ${license}`)
      }
    }
  }
  if (total === 0) throw new Error('No production packages were included in the license report')
  return { total, violations }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const includeDev = process.argv.includes('--include-dev')
  const report = JSON.parse(
    execFileSync(
      'pnpm',
      [
        '--filter',
        '@knowledge/web',
        '--fail-if-no-match',
        'licenses',
        'list',
        ...(includeDev ? [] : ['--prod']),
        '--json',
      ],
      {
        cwd: fileURLToPath(new URL('../', import.meta.url)),
        encoding: 'utf8',
        maxBuffer: 16 * 1024 * 1024,
      },
    ),
  )
  const { total, violations } = validateLicenseReport(report, {
    scope: includeDev ? 'development' : 'production',
  })
  if (violations.length) {
    console.error('Licenses outside the repository allowlist:\n' + violations.join('\n'))
    process.exitCode = 1
  } else {
    console.log(
      `Web ${includeDev ? 'production and development' : 'production'} licenses OK: ${total} packages`,
    )
  }
}
