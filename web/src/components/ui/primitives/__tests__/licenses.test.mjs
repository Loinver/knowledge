import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  isAllowedLicense,
  validateLicenseReport,
} from '../../../../../../scripts/check-web-licenses.mjs'

test('task exceptions require the exact package, version set, and license expression', () => {
  const pkg = { name: 'type-fest', versions: ['4.41.0'] }
  assert.equal(isAllowedLicense('(MIT OR CC0-1.0)', pkg), true)
  for (const license of [
    'CC0-1.0',
    'UNKNOWN',
    'UNLICENSED',
    'MIT OR CC0-1.0',
    '(MIT OR GPL-3.0)',
  ]) {
    assert.equal(isAllowedLicense(license, pkg), false, license)
  }
  for (const pkg of [
    { name: 'another-package', versions: ['4.41.0'] },
    { name: 'type-fest', versions: ['4.40.1'] },
    { name: 'type-fest', versions: ['4.41.0', '5.0.0'] },
    { name: 'type-fest', versions: [] },
  ]) {
    assert.equal(isAllowedLicense('(MIT OR CC0-1.0)', pkg), false)
  }
  const tslib = { name: 'tslib', versions: ['2.8.1'] }
  assert.equal(isAllowedLicense('0BSD', tslib), true)
  for (const license of [
    '(0BSD OR MIT)',
    '0BSD OR MIT',
    'CC0-1.0',
    'UNKNOWN',
    'GPL-3.0',
    'MPL-2.0',
    'BlueOak-1.0.0',
  ]) {
    assert.equal(isAllowedLicense(license, tslib), false, license)
  }
  for (const pkg of [
    { name: 'other-package', versions: ['2.8.1'] },
    { name: 'tslib', versions: ['2.8.0'] },
    { name: 'tslib', versions: ['2.8.2'] },
    { name: 'tslib', versions: ['2.8.1', '2.8.2'] },
    { name: 'tslib', versions: [] },
    { name: 'tslib', versions: '2.8.1' },
    null,
  ]) {
    assert.equal(isAllowedLicense('0BSD', pkg), false)
  }
})

test('reviewed MIT selection does not hide forbidden production packages', () => {
  const result = validateLicenseReport({
    MIT: [{ name: 'reka-ui', versions: ['2.11.0'] }],
    '(MIT OR CC0-1.0)': [{ name: 'type-fest', versions: ['4.41.0'] }],
    '0BSD': [{ name: 'tslib', versions: ['2.8.1'] }],
    'GPL-3.0': [{ name: 'forbidden', versions: ['1.0.0'] }],
  })
  assert.equal(result.total, 4)
  assert.deepEqual(result.violations, ['forbidden@1.0.0: GPL-3.0'])
})

test('MPL exception is limited to the exact approved build packages and version', () => {
  const scope = { scope: 'development' }
  for (const name of ['lightningcss', 'lightningcss-darwin-x64', 'lightningcss-linux-x64-gnu']) {
    const pkg = { name, versions: ['1.33.0'] }
    assert.equal(isAllowedLicense('MPL-2.0', pkg, scope), true)
    assert.equal(isAllowedLicense('MPL-2.0', pkg), false)
  }
  for (const pkg of [
    { name: 'lightningcss-unreviewed', versions: ['1.33.0'] },
    { name: 'lightningcss', versions: ['1.33.1'] },
    { name: 'lightningcss', versions: ['1.33.0', '1.32.0'] },
    { name: 'lightningcss', versions: [] },
  ])
    assert.equal(isAllowedLicense('MPL-2.0', pkg, scope), false)
  const report = { 'MPL-2.0': [{ name: 'lightningcss', versions: ['1.33.0'] }] }
  assert.equal(validateLicenseReport(report, scope).violations.length, 0)
  assert.equal(validateLicenseReport(report).violations.length, 1)
})

test('empty and malformed reports fail instead of becoming a passing scan', () => {
  for (const report of [{}, null, [], { MIT: {} }, { MIT: [{ name: 'missing-versions' }] }]) {
    assert.throws(() => validateLicenseReport(report))
  }
})
