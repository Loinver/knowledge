import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { test } from 'node:test'

import { reactive, watch } from 'vue'

import { compile, mount as mountForm, root } from '../../../../testing/view-harness.mjs'
import { deferred, mount, settle } from '../../relation-types/__tests__/c1-view-harness.mjs'

const entity = (id = 1, props = []) => ({
  id,
  name: `Entity${id}`,
  iri: `https://example.org/Entity${id}`,
  namespace_id: 1,
  status: 'DRAFT',
  current_revision: 2,
  edit_revision: 8,
  label_i18n: { 'zh-CN': '实体' },
  data_props: props,
})
const draft = (extra = {}) => ({
  name: 'Amount',
  label_i18n: { 'zh-CN': '数额', 'en-US': '' },
  definition_i18n: { 'zh-CN': '', 'en-US': '' },
  datatype: 'decimal',
  nullable: true,
  enum_dict_id: null,
  enum_dict_revision: null,
  default_value: null,
  min_cardinality: null,
  max_cardinality: null,
  min_value: null,
  max_value: null,
  source_clause_ref: null,
  ...extra,
})
const context = { editingName: null, names: [] }
const version = { id: 10, revision: 2, entries: [{ value: '0' }, { value: 'false' }] }
const mountEntity = (api = {}, transform) =>
  mount(
    'views/semantic-assets/entity-types/EntityTypeDetailPage.vue',
    {
      '@/api/entity-types': {
        entityTypesApi: {
          get: async (id) => entity(id),
          list: async () => [],
          usages: async () => ({}),
          ...api,
        },
      },
      '@/api/enum-dictionaries': {
        enumDictionariesApi: {
          list: async () => ({ items: [] }),
          revisions: async () => [],
        },
      },
    },
    'data,form,openProperty,submitProperty,propertyFormRef,propertyFormRules,propertyValidating,propertySession,showEditor,busy,editorError,error,notice,versions,versionsLoading,auth,locale,setLocaleMessage',
    '/entities/1',
    (source) =>
      (transform ? transform(source) : source).replace(
        'const { t, locale } = useI18n()',
        'const { t, locale, setLocaleMessage } = useI18n()',
      ),
  )

test('cardinality accepts exact safe integers, rejects invalid text without clamping, and applies nullable minimum', async (t) => {
  const built = await compile('views/semantic-assets/entity-types/propertyValidation.ts')
  t.after(built.cleanup)
  const { propertyErrors, cardinalityValue } = built.mod
  for (const value of [0, 1, Number.MAX_SAFE_INTEGER, '0', '9007199254740991', null])
    assert.equal(
      propertyErrors(draft({ min_cardinality: value }), context).min_cardinality,
      undefined,
    )
  for (const value of [
    -1,
    0.5,
    Number.MAX_SAFE_INTEGER + 1,
    Infinity,
    NaN,
    false,
    '-1',
    '1.0',
    '9007199254740990.9',
    '9007199254740992',
    '1e2',
    ' 1',
    '1\n',
    '',
  ]) {
    assert.equal(cardinalityValue(value), undefined, String(value))
    for (const field of ['min_cardinality', 'max_cardinality'])
      assert.equal(
        propertyErrors(draft({ [field]: value }), context)[field],
        'entityProps.invalidCardinality',
      )
  }
  for (const extra of [
    { min_cardinality: 2, max_cardinality: 1 },
    { nullable: false, min_cardinality: null, max_cardinality: 0 },
    { nullable: false, min_cardinality: 0, max_cardinality: 0 },
  ])
    assert.equal(
      propertyErrors(draft(extra), context).max_cardinality,
      'entityProps.cardinalityOrder',
    )
  assert.deepEqual(propertyErrors(draft({ min_cardinality: 0, max_cardinality: 0 }), context), {})
  assert.deepEqual(propertyErrors(draft({ nullable: false, max_cardinality: null }), context), {})
})

test('numeric bounds follow decimal lexical limits and integral semantics without float rounding', async (t) => {
  const built = await compile('views/semantic-assets/entity-types/propertyValidation.ts')
  t.after(built.cleanup)
  const { propertyErrors, propertyPayload } = built.mod
  for (const value of ['0', '-0', '+001.00', '1.', '.5', '-.5', '9'.repeat(256)]) {
    const input = draft({ min_value: value })
    assert.deepEqual(propertyErrors(input, context), {}, value)
    assert.equal(propertyPayload(input).min_value, value)
  }
  for (const value of [
    '',
    ' ',
    ' 1',
    '1 ',
    '1\n',
    '1e3',
    'NaN',
    'Infinity',
    '0x10',
    '1,2',
    '１',
    '9'.repeat(257),
    0,
    false,
  ])
    assert.equal(
      propertyErrors(draft({ min_value: value }), context).min_value,
      'entityProps.invalidNumericBound',
      String(value),
    )
  for (const datatype of ['string', 'boolean', 'date', 'enum', 'anyURI'])
    assert.equal(
      propertyErrors(draft({ datatype, min_value: '0' }), context).min_value,
      'entityProps.rangeDatatype',
    )
  for (const value of ['9007199254740993.0', '-123.000', '+0.', '-.0'])
    assert.equal(
      propertyErrors(draft({ datatype: 'integer', min_value: value }), context).min_value,
      undefined,
    )
  for (const value of ['9007199254740993.0000000000000000001', '0.0000000000000000001'])
    assert.equal(
      propertyErrors(draft({ datatype: 'integer', min_value: value }), context).min_value,
      'entityProps.invalidNumericBound',
    )
  for (const [min_value, max_value] of [
    ['9007199254740993', '9007199254740992'],
    ['0.1000000000000000002', '0.1000000000000000001'],
    ['-0.1000000000000000001', '-0.1000000000000000002'],
    ['-999', '-1000'],
    ['.0001', '-0'],
  ])
    assert.equal(
      propertyErrors(draft({ min_value, max_value }), context).max_value,
      'entityProps.numericOrder',
    )
  for (const [min_value, max_value] of [
    ['+0001.00', '1'],
    ['-0', '+.0'],
    ['-1000', '-999'],
    ['-0.01', '0.01'],
    ['.00001', '.0001'],
    ['9'.repeat(255), `1${'0'.repeat(255)}`],
  ])
    assert.deepEqual(propertyErrors(draft({ min_value, max_value }), context), {})
})

test('invalid property fields never write or silently repair the draft, even if a form stub resolves', async (t) => {
  const writes = []
  const ctx = await mountEntity({ update: async (...args) => writes.push(args) })
  t.after(ctx.stop)
  ctx.vm.openProperty()
  ctx.vm.propertyFormRef = { validate: async () => {}, restoreValidation() {} }
  for (const invalid of [
    { name: 'lowercase' },
    { name: 'Name\n' },
    { name: 'A'.repeat(129) },
    { label_i18n: { 'zh-CN': '   ' } },
    { min_cardinality: -1 },
    { min_cardinality: NaN },
    { min_cardinality: Infinity },
    { max_cardinality: Infinity },
    { max_cardinality: 0.5 },
    { min_cardinality: 2, max_cardinality: 1 },
    { nullable: false, max_cardinality: 0 },
    { min_cardinality: '9007199254740990.9' },
    { min_value: '1e3' },
    { datatype: 'integer', max_value: '1.01' },
    { datatype: 'string', min_value: '0' },
    { min_value: '9007199254740993', max_value: '9007199254740992' },
    { min_value: '0.1000000000000000002', max_value: '0.1000000000000000001' },
    { default_value: false },
  ]) {
    ctx.vm.form = draft(invalid)
    const before = JSON.stringify(ctx.vm.form)
    await ctx.vm.submitProperty()
    assert.equal(JSON.stringify(ctx.vm.form), before)
    assert.equal(ctx.vm.showEditor, true)
    assert.equal(ctx.vm.propertyValidating, false)
    assert.deepEqual(writes, [], JSON.stringify(invalid))
  }
})

test('test_any_uri_defaults_match_reference_lexical_rules_and_invalid_values_never_write', async (t) => {
  const built = await compile('views/semantic-assets/entity-types/propertyValidation.ts')
  const vee = await compile('components/business/formValidation.ts')
  t.after(built.cleanup)
  t.after(vee.cleanup)
  const { propertyErrors, propertyRules, propertyPayload } = built.mod
  const invalid = [
    'bad value',
    ' bad',
    'bad\tvalue',
    'bad\nvalue',
    'bad\u0000value',
    'bad\u007fvalue',
    'bad\u0085value',
    'bad\u3000value',
    ...['<', '>', '"', '{', '}', '|', '\\', '^', '`'].map((char) => `bad${char}value`),
    'bad%escape',
    'bad%',
    'bad%2',
    'https://[invalid',
    'https://invalid]',
    'https://[invalid]',
    'https://[127.0.0.1]',
    'https://before[::1]',
    'https://[::1]after',
    'https://[vG.host]',
    'https://example.com\uFF0Fpath',
  ]
  const valid = [
    null,
    '',
    '../relative',
    '../资料/条目%20一',
    'urn:example:test',
    '/资料/条目',
    '资料/条目',
    '?query=%20',
    '#片段',
    'https://例子.example/条目%20一',
    'https://[::1]/',
    '//[2001:db8::1]:not-a-port/path',
    'urn://[v1.host]/path',
    '//[fe80::1%25eth0]/path',
    'relative[brackets]',
  ]
  for (const value of [...invalid, ...valid]) {
    const input = draft({ datatype: 'anyURI', default_value: value })
    const expected = invalid.includes(value) ? 'entityProps.invalidUriDefault' : undefined
    assert.equal(propertyErrors(input, context).default_value, expected, JSON.stringify(value))
    const rule = propertyRules(input, context, (key) => key).default_value
    assert.equal(
      await vee.mod.validateFieldValue(value, [rule], 'Required'),
      expected,
      JSON.stringify(value),
    )
    assert.equal(propertyPayload(input).default_value, value)
  }
  const writes = []
  const existing = draft({ name: 'Link', datatype: 'anyURI', default_value: '../relative' })
  const ctx = await mountEntity({
    get: async (id) => entity(id, [existing]),
    update: async (id, payload) => {
      writes.push({ id, payload })
      return { ...entity(id), ...payload }
    },
  })
  t.after(ctx.stop)
  ctx.vm.openProperty(existing)
  ctx.vm.propertyFormRef = { validate: async () => {}, restoreValidation() {} }
  for (const value of invalid) {
    ctx.vm.form.default_value = value
    const before = JSON.stringify(ctx.vm.form)
    await ctx.vm.submitProperty()
    assert.equal(writes.length, 0, JSON.stringify(value))
    assert.equal(JSON.stringify(ctx.vm.form), before)
    assert.equal(ctx.vm.showEditor, true)
  }
  const value = '../资料/条目%20一'
  ctx.vm.form.default_value = value
  await ctx.vm.submitProperty()
  assert.equal(writes.length, 1)
  assert.equal(writes[0].payload.data_props[0].default_value, value)
  assert.equal(writes[0].payload.if_match, 2)
  assert.equal(writes[0].payload.edit_revision, 8)
})

test('successful property writes preserve zero, false, null, exact numeric strings and revision guards', async (t) => {
  const writes = []
  const ctx = await mountEntity({
    update: async (id, payload) => {
      writes.push({ id, payload })
      return { ...entity(id), ...payload }
    },
  })
  t.after(ctx.stop)
  for (const default_value of ['0', 'false', null]) {
    ctx.vm.data = entity()
    ctx.vm.openProperty()
    ctx.vm.form = draft({
      nullable: false,
      default_value,
      min_cardinality: '0',
      max_cardinality: null,
      datatype: 'integer',
      min_value: '+009007199254740993.000',
      max_value: '9007199254740994.0',
    })
    await ctx.vm.submitProperty()
    assert.equal(ctx.vm.showEditor, false)
    assert.equal(ctx.vm.busy, false)
    assert.equal(ctx.vm.propertyValidating, false)
    const { id, payload } = writes.at(-1)
    assert.equal(id, 1)
    assert.equal(payload.if_match, 2)
    assert.equal(payload.edit_revision, 8)
    const prop = payload.data_props[0]
    assert.equal(prop.min_cardinality, 0)
    assert.equal(prop.max_cardinality, null)
    assert.equal(prop.nullable, false)
    assert.equal(prop.default_value, default_value)
    assert.equal(prop.min_value, '+009007199254740993.000')
    assert.equal(prop.max_value, '9007199254740994.0')
    assert.equal(prop.enum_dict_id, null)
    assert.equal(prop.source_clause_ref, null)
  }
})

test('legal legacy names survive editing while duplicate names, enum pin and default constraints remain enforced', async (t) => {
  const writes = []
  const legacy = draft({
    name: 'legacy_code',
    datatype: 'enum',
    enum_dict_id: 10,
    enum_dict_revision: 2,
  })
  const ctx = await mountEntity({
    get: async (id) => entity(id, [legacy, draft({ name: 'Other' })]),
    update: async (id, payload) => {
      writes.push(payload)
      return { ...entity(id), ...payload }
    },
  })
  t.after(ctx.stop)
  ctx.vm.openProperty(legacy)
  await settle()
  ctx.vm.versions = [version]
  ctx.vm.form.default_value = 'false'
  await ctx.vm.submitProperty()
  assert.equal(writes[0].data_props[0].name, 'legacy_code')
  assert.equal(writes[0].data_props[0].default_value, 'false')
  ctx.vm.openProperty()
  ctx.vm.form = draft({ name: 'Other' })
  await ctx.vm.submitProperty()
  assert.equal(ctx.vm.editorError, 'This entity already has a property with this name.')
  for (const changes of [
    { enum_dict_id: null },
    { enum_dict_revision: null },
    { enum_dict_revision: 3 },
    { enum_dict_id: 11 },
    { default_value: 'removed' },
  ]) {
    ctx.vm.form = draft({ datatype: 'enum', enum_dict_id: 10, enum_dict_revision: 2, ...changes })
    ctx.vm.versions = [version]
    await ctx.vm.submitProperty()
    assert.equal(writes.length, 1)
    assert.equal(ctx.vm.showEditor, true)
  }
})

test('validation locks duplicate submissions and captures the original property input', async (t) => {
  const validation = deferred()
  const writes = []
  const ctx = await mountEntity({
    update: async (id, payload) => {
      writes.push(payload)
      return { ...entity(id), ...payload }
    },
  })
  t.after(ctx.stop)
  ctx.vm.openProperty()
  ctx.vm.form = draft({ min_value: '0.1000000000000000001', max_value: '0.1000000000000000002' })
  ctx.vm.propertyFormRef = { validate: () => validation.promise, restoreValidation() {} }
  const saving = ctx.vm.submitProperty()
  assert.equal(ctx.vm.propertyValidating, true)
  const session = ctx.vm.propertySession
  ctx.vm.openProperty()
  assert.equal(ctx.vm.propertySession, session)
  await ctx.vm.submitProperty()
  validation.resolve()
  await saving
  assert.equal(writes.length, 1)
  assert.equal(writes[0].data_props[0].min_value, '0.1000000000000000001')
})

test('late validation success or failure cannot write, unlock or overwrite a newer editor session', async (t) => {
  for (const fail of [false, true]) {
    const old = deferred()
    const current = deferred()
    const writes = []
    const ctx = await mountEntity({ update: async (...args) => writes.push(args) })
    t.after(ctx.stop)
    ctx.vm.openProperty()
    ctx.vm.form = draft()
    ctx.vm.propertyFormRef = { validate: () => old.promise, restoreValidation() {} }
    const saving = ctx.vm.submitProperty()
    ctx.vm.showEditor = false
    ctx.vm.openProperty()
    ctx.vm.form = draft({ name: 'Next', label_i18n: { 'zh-CN': '下一会话' } })
    ctx.vm.propertyFormRef = { validate: () => current.promise, restoreValidation() {} }
    const next = ctx.vm.submitProperty()
    if (fail) old.reject(new Error('FORM_INVALID'))
    else old.resolve()
    await saving
    assert.deepEqual(writes, [])
    assert.equal(ctx.vm.propertyValidating, true)
    assert.equal(ctx.vm.showEditor, true)
    assert.equal(ctx.vm.form.name, 'Next')
    assert.equal(ctx.vm.editorError, '')
    current.reject(new Error('FORM_INVALID'))
    await next
    assert.equal(ctx.vm.propertyValidating, false)
    assert.equal(ctx.vm.form.label_i18n['zh-CN'], '下一会话')
  }
})

test('navigation, unmount and permissions invalidate a pending property validation', async (t) => {
  for (const action of ['navigate', 'unmount', 'viewer', 'edit']) {
    const pending = deferred()
    const writes = []
    const ctx = await mountEntity({ update: async (...args) => writes.push(args) })
    if (action !== 'unmount') t.after(ctx.stop)
    ctx.vm.openProperty()
    ctx.vm.form = draft()
    ctx.vm.propertyFormRef = { validate: () => pending.promise, restoreValidation() {} }
    const saving = ctx.vm.submitProperty()
    if (action === 'navigate') {
      await ctx.router.push('/entities/2')
      await settle()
      ctx.vm.openProperty()
      ctx.vm.form.name = 'NewEntityProperty'
    } else if (action === 'unmount') ctx.stop()
    else if (action === 'viewer') ctx.vm.auth.user.role = 'VIEWER'
    else ctx.vm.form.min_value = '0.1000000000000000001'
    pending.resolve()
    await saving
    assert.deepEqual(writes, [])
    if (action === 'navigate') assert.equal(ctx.vm.form.name, 'NewEntityProperty')
  }
})

test('obsolete property request responses cannot replace a newer entity or clear its pending write', async (t) => {
  for (const fail of [false, true]) {
    const old = deferred()
    const current = deferred()
    const ctx = await mountEntity({ update: (id) => (id === 1 ? old.promise : current.promise) })
    t.after(ctx.stop)
    ctx.vm.openProperty()
    ctx.vm.form = draft()
    const first = ctx.vm.submitProperty()
    await settle()
    await ctx.router.push('/entities/2')
    await settle()
    ctx.vm.openProperty()
    ctx.vm.form = draft({ name: 'Current' })
    const second = ctx.vm.submitProperty()
    await settle()
    if (fail) old.reject({ code: 'KG.REVISION_CONFLICT' })
    else old.resolve(entity(1))
    await first
    assert.equal(ctx.vm.data.id, 2)
    assert.equal(ctx.vm.busy, true)
    assert.equal(ctx.vm.showEditor, true)
    assert.equal(ctx.vm.form.name, 'Current')
    assert.equal(ctx.vm.editorError, '')
    current.reject({ code: 'KG.REVISION_CONFLICT' })
    await second
    assert.equal(ctx.vm.busy, false)
    assert.equal(ctx.vm.propertyValidating, false)
    assert.ok(ctx.vm.editorError)
  }
})

test('real FormContainer revalidates only existing cross-field errors and retranslates them in an open form', async (t) => {
  const ctx = await mountEntity()
  t.after(ctx.stop)
  const zh = JSON.parse(await readFile(path.join(root, 'web/src/locales/zh-CN.json'), 'utf8'))
  ctx.vm.setLocaleMessage('zh-CN', zh)
  ctx.vm.openProperty()
  ctx.vm.form = draft({ min_cardinality: 2, max_cardinality: 1, min_value: '2', max_value: '1' })
  const rules = reactive({ ...ctx.vm.propertyFormRules })
  const stop = watch(
    () => ctx.vm.propertyFormRules,
    (next) => Object.assign(rules, next),
    { flush: 'sync' },
  )
  t.after(stop)
  const form = await mountForm(
    'components/business/FormContainer.vue',
    {},
    'errors,validate',
    '/',
    (source) => source.replace('defineExpose<FormInst>({ validate, restoreValidation })', ''),
    'EDITOR',
    { model: ctx.vm.form, rules },
  )
  t.after(form.stop)
  await assert.rejects(form.vm.validate())
  assert.deepEqual(Object.keys(form.vm.errors).sort(), ['max_cardinality', 'max_value'])
  ctx.vm.locale = 'zh-CN'
  await settle()
  assert.equal(form.vm.errors.max_cardinality, zh.entityProps.cardinalityOrder)
  assert.equal(form.vm.errors.max_value, zh.entityProps.numericOrder)
  // Correct the other endpoint, leaving the errored controls untouched.
  ctx.vm.form.min_cardinality = 0
  ctx.vm.form.min_value = '0'
  await settle()
  assert.deepEqual(form.vm.errors, {})
  ctx.vm.form.max_cardinality = 0
  ctx.vm.form.nullable = false
  await settle()
  assert.deepEqual(form.vm.errors, {}) // Untouched invalid fields are not flooded with errors.
  await assert.rejects(form.vm.validate())
  assert.equal(form.vm.errors.max_cardinality, zh.entityProps.cardinalityOrder)
  ctx.vm.form.nullable = true
  await settle()
  assert.deepEqual(form.vm.errors, {})
  ctx.vm.form.datatype = 'enum'
  ctx.vm.form.min_value = null
  ctx.vm.form.max_value = null
  ctx.vm.form.enum_dict_id = 10
  ctx.vm.form.enum_dict_revision = 2
  ctx.vm.form.default_value = 'removed'
  ctx.vm.versions = [version]
  await settle()
  await assert.rejects(form.vm.validate())
  assert.equal(form.vm.errors.default_value, zh.entityProps.invalidDefault)
  ctx.vm.versions = [{ ...version, entries: [{ value: 'removed' }] }]
  await settle()
  assert.deepEqual(form.vm.errors, {})
})

test('Vee rules associate nested fields and keep zero, false and null distinct', async (t) => {
  const built = await compile('views/semantic-assets/entity-types/propertyValidation.ts')
  const vee = await compile('components/business/formValidation.ts')
  t.after(built.cleanup)
  t.after(vee.cleanup)
  const input = draft({ min_cardinality: 0, nullable: false })
  const rules = built.mod.propertyRules(input, context, (key) => key)
  for (const field of ['min_cardinality', 'nullable', 'default_value', 'label_i18n.zh-CN'])
    assert.equal(
      await vee.mod.validateFieldValue(vee.mod.readField(input, field), [rules[field]], 'Required'),
      undefined,
    )
  input.min_cardinality = -1
  assert.equal(
    await vee.mod.validateFieldValue(input.min_cardinality, [rules.min_cardinality], 'Required'),
    'entityProps.invalidCardinality',
  )
  assert.equal(input.min_cardinality, -1)
})

test('invalid submit keeps the duplicate guard while real FormContainer focuses the first enabled field', async (t) => {
  const writes = []
  const ctx = await mountEntity({ update: async (...args) => writes.push(args) })
  t.after(ctx.stop)
  ctx.vm.openProperty()
  const form = await mountForm(
    'components/business/FormContainer.vue',
    {},
    'validate,registered,blocked',
    '/',
    (source) => source.replace('defineExpose<FormInst>({ validate, restoreValidation })', ''),
    'EDITOR',
    { model: ctx.vm.form, rules: ctx.vm.propertyFormRules, disabled: false, submitting: false },
  )
  t.after(form.stop)
  let focused = ''
  form.vm.registered.set('name', () => ({
    querySelector: () => ({
      focus() {
        assert.equal(ctx.vm.propertyValidating, true)
        assert.equal(form.vm.blocked, false)
        focused = 'name'
      },
    }),
  }))
  ctx.vm.propertyFormRef = { validate: form.vm.validate, restoreValidation() {} }
  const submitting = ctx.vm.submitProperty()
  await ctx.vm.submitProperty()
  await submitting
  assert.equal(focused, 'name')
  assert.deepEqual(writes, [])
  assert.equal(ctx.vm.propertyValidating, false)
})
