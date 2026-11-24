import assert from 'node:assert/strict'
import { test } from 'node:test'

import { compile } from '../../../testing/view-harness.mjs'

test('Field validation distinguishes empty values, zero and false with nested paths', async (t) => {
  const built = await compile('components/business/formValidation.ts')
  t.after(built.cleanup)
  const { readField, validateFieldValue } = built.mod
  const model = { fields: [{ count: 0, enabled: false, label: '' }] }
  assert.equal(readField(model, 'fields[0].count'), 0)
  assert.equal(readField(model, 'fields.0.enabled'), false)
  assert.equal(
    await validateFieldValue(0, [{ required: true, type: 'number' }], 'Required'),
    undefined,
  )
  assert.equal(
    await validateFieldValue(false, [{ required: true, type: 'boolean' }], 'Required'),
    undefined,
  )
  for (const empty of [null, undefined, '', '  ', []]) {
    assert.equal(await validateFieldValue(empty, [{ required: true }], 'Required'), 'Required')
  }
  assert.equal(await validateFieldValue('0', [{ type: 'number' }], 'Invalid'), 'Invalid')
})

test('cross-field and asynchronous rules produce field feedback without changing model types', async (t) => {
  const built = await compile('components/business/formValidation.ts')
  t.after(built.cleanup)
  const model = { password: 'Secret', confirm: 'Different', amount: 0, enabled: false }
  const rules = [{ validator: (_rule, value) => value === model.password, message: 'Mismatch' }]
  assert.equal(await built.mod.validateFieldValue(model.confirm, rules, 'Invalid'), 'Mismatch')
  model.confirm = 'Secret'
  assert.equal(await built.mod.validateFieldValue(model.confirm, rules, 'Invalid'), undefined)
  assert.equal(
    await built.mod.validateFieldValue(
      'taken',
      [{ validator: async () => new Error('Already used') }],
      'Invalid',
    ),
    'Already used',
  )
  assert.deepEqual(model, { password: 'Secret', confirm: 'Secret', amount: 0, enabled: false })
})
