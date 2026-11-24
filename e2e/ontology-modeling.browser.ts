import type { APIRequestContext } from '@playwright/test'

import type { components } from '../web/src/api/schema'
import { capture, expect, responseData, test, uniqueName } from './ui-redesign-fixtures'

type Schemas = components['schemas']
async function configureChat(api: APIRequestContext) {
  const model = await responseData<Schemas['AiModelConfigOut']>(
    await api.post('/api/v1/ai/model-configs', {
      data: {
        name: 'Fictional modeling fixture',
        capability: 'CHAT',
        base_url: 'http://127.0.0.1:8134/v1',
        model: 'ontology-candidate-fixture',
        model_version: 'synthetic-v1',
        timeout_seconds: 30,
        enabled: true,
        api_key: 'isolated-test-key',
      },
    }),
  )
  const defaults = await responseData<Schemas['AiModelDefaultOut'][]>(
    await api.get('/api/v1/ai/model-defaults'),
  )
  const chat = defaults.find((entry) => entry.capability === 'CHAT')!
  await responseData(
    await api.put('/api/v1/ai/model-defaults/CHAT', {
      headers: { 'If-Match': String(chat.revision) },
      data: { config_id: model.id },
    }),
  )
}
async function createTarget(api: APIRequestContext) {
  const namespace = await responseData<Schemas['NamespaceOut']>(
    await api.post('/api/v1/namespaces', {
      data: {
        prefix: uniqueName('fixture'),
        iri: `https://example.org/${uniqueName('fiction')}/`,
        label_i18n: { 'zh-CN': '虚构验收命名空间' },
      },
    }),
  )
  const ontology = await responseData<Schemas['OntologyOut']>(
    await api.post('/api/v1/ontologies', {
      data: {
        name: uniqueName('FictionalOntology'),
        iri: `https://example.org/${uniqueName('ontology')}`,
        label_i18n: { 'zh-CN': '纯虚构建模验收本体' },
        ref_resource_ids: [],
        rule_ids: [],
      },
    }),
  )
  return { namespace, ontology }
}

test('real backend with local synthetic model: generate validate confirm apply and refresh draft references', async ({
  signedIn: page,
  identity,
  evidence,
}, info) => {
  await configureChat(identity.api)
  const { namespace, ontology } = await createTarget(identity.api)
  await page.goto(`/ontology/designer?ontology=${ontology.id}`)
  const open = page.getByRole('button', { name: 'AI 本体建模', exact: true })
  await expect(open).toBeEnabled()
  await open.click()
  const panel = page.locator('.modeling-panel')
  await expect(panel).toBeVisible()
  const generate = panel.getByRole('button', { name: '生成建模候选', exact: true })
  const proposalWrites: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/ai/ontology-modeling/proposals'))
      proposalWrites.push(request.url())
  })
  await expect(generate).toBeEnabled()
  await generate.click()
  await expect(panel.locator('.ui-field-error').first()).toBeVisible()
  expect(proposalWrites).toEqual([])
  await panel.getByRole('combobox', { name: /命名空间/ }).click()
  await page
    .getByRole('option', { name: `${namespace.prefix} · ${namespace.iri}`, exact: true })
    .click()
  await panel
    .locator('textarea')
    .first()
    .fill('纯虚构验收：创建虚构设备和虚构团队，以虚构分配关系连接。所有内容仅供本地自动化测试。')
  await panel.getByRole('checkbox', { name: /我确认有权提供上述资料/ }).click()
  await expect(generate).toBeEnabled()
  const generated = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      response.url().endsWith('/ai/ontology-modeling/proposals'),
  )
  await generate.click()
  const proposal = await responseData<Schemas['ModelingProposalOut']>(await generated)
  expect(proposalWrites).toHaveLength(1)
  expect(proposal.candidate.resources).toHaveLength(3)
  await expect(panel).toContainText('虚构设备')
  await expect(panel).toContainText('未翻译')
  const validating = page.waitForResponse((response) =>
    response.url().endsWith(`/proposals/${proposal.id}/validate`),
  )
  await panel.getByRole('button', { name: '校验当前候选', exact: true }).click()
  const validation = await responseData<Schemas['ModelingValidationOut']>(await validating)
  expect(validation.can_apply, JSON.stringify(validation.checks)).toBe(true)
  const apply = panel.getByRole('button', { name: '确认应用到草稿', exact: true })
  await expect(apply).toBeDisabled()
  await panel.getByRole('checkbox', { name: /我已审阅上方改动/ }).click()
  await expect(apply).toBeEnabled()
  await capture(
    page,
    info,
    evidence,
    'validated-proposal',
    'real backend validation of a fictional ontology candidate from localhost:8134; no external model',
  )
  const applying = page.waitForResponse((response) =>
    response.url().endsWith(`/proposals/${proposal.id}/apply`),
  )
  await apply.click()
  const response = await applying
  const request = response.request()
  expect(request.headers()['if-match']).toBe(String(proposal.revision))
  expect(request.headers()['idempotency-key']).toBeTruthy()
  const payload = request.postDataJSON() as Schemas['ModelingApply']
  expect(payload.confirmation.accepted_plan_digest).toBe(validation.compiled_plan_digest)
  const application = await responseData<Schemas['ModelingApplyOut']>(response)
  expect(application.state).toBe('APPLIED_TO_DRAFT')
  await expect(panel).not.toBeVisible()
  const detail = await responseData<Schemas['OntologyOut']>(
    await identity.api.get(`/api/v1/ontologies/${ontology.id}`),
  )
  expect(detail.edit_revision).toBe(application.after_edit_revision)
  expect(detail.status).toBe('DRAFT')
  const refs = await responseData<Schemas['OntologyRefOut'][]>(
    await identity.api.get(`/api/v1/ontologies/${ontology.id}/refs`),
  )
  expect(refs.length).toBeGreaterThanOrEqual(3)
  await expect(page.locator('.canvas')).toContainText('虚构设备')
  await expect(page.locator('.canvas')).toContainText('虚构团队')
  await capture(
    page,
    info,
    evidence,
    'applied-working-draft',
    'real atomic application receipt and refreshed Designer references; draft remains unpublished',
  )
})

test.describe('viewer', () => {
  test.use({ role: 'VIEWER' })
  test('viewer cannot open the modeling mutation workflow', async ({
    signedIn: page,
    identity,
  }) => {
    const { ontology } = await createTarget(identity.api)
    await page.goto(`/ontology/designer?ontology=${ontology.id}`)
    await expect(page.getByRole('button', { name: 'AI 本体建模', exact: true })).toBeDisabled()
    await expect(page.locator('.modeling-panel')).toHaveCount(0)
  })
})
