import { expect } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'

import type { AiModelConfig, AiModelDefault, AiModelPage } from '../web/src/api/ai-models'
import {
  capture,
  expectNoPageOverflow,
  getData,
  responseData,
  settleApi,
  test,
  uniqueName,
  waitForApi,
} from './ui-redesign-fixtures'

const configsPath = '/ai/model-configs'
const defaultsPath = '/ai/model-defaults'
const fakeUrl = 'http://127.0.0.1:9/v1'
const replacementUrl = 'http://127.0.0.1:10/v1'
const fakeKey = 'fakekey-ai-model-ui'
const replacementKey = 'fakekey-ai-model-replacement'

function editor(page: Page) {
  return page.getByRole('dialog').and(page.locator('.ui-sheet')).last()
}

function row(page: Page, name: string) {
  return page.locator('tr').filter({ hasText: name }).first()
}

async function pickCapability(page: Page, label: string): Promise<void> {
  await editor(page)
    .getByRole('combobox', { name: /^模型类别(?:\s*此项必填)?$/ })
    .click()
  await page.getByRole('option', { name: label, exact: true }).click()
}

function expectSecretHidden(configuration: AiModelConfig): void {
  expect(configuration).not.toHaveProperty('api_key')
  expect(configuration).not.toHaveProperty('encrypted_key')
  expect(configuration.api_key_mask).toBe(configuration.has_key ? '***' : null)
  const serialized = JSON.stringify(configuration)
  expect(serialized).not.toContain(fakeKey)
  expect(serialized).not.toContain(replacementKey)
}

async function openEditor(page: Page, name: string): Promise<void> {
  await row(page, name).getByRole('button', { name: '编辑', exact: true }).click()
  await expect(editor(page).getByLabel(/^配置名称(?:\s*此项必填)?$/)).toHaveValue(name)
  await expect(editor(page).getByLabel('API 密钥', { exact: true })).toHaveValue('')
  await expect(editor(page).getByRole('button', { name: '保存', exact: true })).toBeEnabled()
}

async function createModel(page: Page, name: string, capability: 'CHAT' | 'EMBEDDING') {
  await page.getByRole('button', { name: '新建模型配置', exact: true }).click()
  await editor(page)
    .getByLabel(/^配置名称(?:\s*此项必填)?$/)
    .fill(name)
  await expect(editor(page).getByLabel(/^服务地址(?:\s*此项必填)?$/)).toHaveValue('')
  await expect(editor(page).getByLabel(/^模型标识(?:\s*此项必填)?$/)).toHaveValue('')
  if (capability === 'EMBEDDING') await pickCapability(page, '向量嵌入')
  await editor(page)
    .getByLabel(/^服务地址(?:\s*此项必填)?$/)
    .fill(fakeUrl)
  await editor(page)
    .getByLabel(/^模型标识(?:\s*此项必填)?$/)
    .fill(capability === 'CHAT' ? 'local-chat-model' : 'local-embedding-model')
  await editor(page).getByLabel('API 密钥', { exact: true }).fill(fakeKey)
  const created = waitForApi(page, { path: configsPath, method: 'POST' })
  await editor(page).getByRole('button', { name: '创建', exact: true }).click()
  const configuration = await responseData<AiModelConfig>(await created)
  expect(configuration).toMatchObject({ name, capability, enabled: false, has_key: true })
  expectSecretHidden(configuration)
  await expect(editor(page)).toHaveCount(0)
  await expect(row(page, name)).toBeVisible()
  return configuration
}

async function saveModel(page: Page, id: number) {
  const saved = waitForApi(page, { path: `${configsPath}/${id}`, method: 'PUT' })
  await editor(page).getByRole('button', { name: '保存', exact: true }).click()
  const response = await saved
  const configuration = await responseData<AiModelConfig>(response)
  expectSecretHidden(configuration)
  await expect(editor(page)).toHaveCount(0)
  return { configuration, request: response.request() }
}

async function enableModel(page: Page, configuration: AiModelConfig) {
  const changed = waitForApi(page, { path: `${configsPath}/${configuration.id}`, method: 'PUT' })
  await row(page, configuration.name).getByRole('button', { name: '启用', exact: true }).click()
  const result = await responseData<AiModelConfig>(await changed)
  expect(result.enabled).toBe(true)
  await expect(row(page, configuration.name).getByText('已启用', { exact: true })).toBeVisible()
  return result
}

async function selectDefault(page: Page, configuration: AiModelConfig) {
  const selected = waitForApi(page, {
    path: `${defaultsPath}/${configuration.capability}`,
    method: 'PUT',
  })
  await row(page, configuration.name).getByRole('button', { name: '设为默认', exact: true }).click()
  const selection = await responseData<AiModelDefault>(await selected)
  expect(selection.config_id).toBe(configuration.id)
  await expect(page.getByTestId(`ai-default-${configuration.capability}`)).toContainText(
    configuration.name,
  )
  return selection
}

/** Restore both global selections before deleting our configurations, even after a failed assertion. */
async function cleanupModels(
  api: APIRequestContext,
  original: AiModelDefault[],
  namePrefix: string,
): Promise<void> {
  const failures: unknown[] = []
  for (const previous of original) {
    try {
      const current = (await getData<AiModelDefault[]>(api, defaultsPath)).find(
        (selection) => selection.capability === previous.capability,
      )
      expect(current, 'Both capability default selections must exist').toBeDefined()
      if (current!.config_id !== previous.config_id) {
        await responseData(
          await api.put('/api/v1' + `${defaultsPath}/${previous.capability}`, {
            headers: { 'If-Match': String(current!.revision) },
            data: { config_id: previous.config_id },
          }),
        )
      }
    } catch (cause) {
      failures.push(cause)
    }
  }
  try {
    const remaining = await getData<AiModelPage>(
      api,
      configsPath + '?q=' + encodeURIComponent(namePrefix) + '&page_size=100',
    )
    for (const configuration of remaining.items.filter((item) =>
      item.name.startsWith(namePrefix),
    )) {
      try {
        const current = await getData<AiModelConfig>(api, `${configsPath}/${configuration.id}`)
        await responseData(
          await api.delete('/api/v1' + `${configsPath}/${current.id}`, {
            headers: { 'If-Match': String(current.revision) },
          }),
        )
      } catch (cause) {
        failures.push(cause)
      }
    }
    expect(
      (await getData<AiModelPage>(api, configsPath + '?q=' + encodeURIComponent(namePrefix))).items,
      'No test model configurations remain',
    ).toEqual([])
    const restored = await getData<AiModelDefault[]>(api, defaultsPath)
    for (const previous of original) {
      expect(
        restored.find((selection) => selection.capability === previous.capability)?.config_id,
      ).toBe(previous.config_id)
    }
  } catch (cause) {
    failures.push(cause)
  }
  if (failures.length) throw new AggregateError(failures, 'AI model test cleanup failed')
}

test('ADMIN manages model CRUD, write-only keys and both defaults without model requests', async ({
  signedIn: page,
  identity,
  evidence,
}, info) => {
  const namePrefix = uniqueName('model_ui_')
  const originalDefaults = await getData<AiModelDefault[]>(identity.api, defaultsPath)
  expect(originalDefaults.map((selection) => selection.capability).sort()).toEqual([
    'CHAT',
    'EMBEDDING',
  ])
  try {
    await page.goto('/system/ai-models')
    await expect(page.getByRole('heading', { name: 'AI 模型配置', exact: true })).toBeVisible()
    await settleApi(page, evidence)
    await expectNoPageOverflow(page)

    let chat = await createModel(page, namePrefix + '_chat', 'CHAT')
    let embedding = await createModel(page, namePrefix + '_embedding', 'EMBEDDING')
    await expect(row(page, chat.name).getByText('对话模型', { exact: true })).toBeVisible()
    await expect(row(page, embedding.name).getByText('向量嵌入', { exact: true })).toBeVisible()
    await expect(
      row(page, chat.name).getByRole('button', { name: '设为默认', exact: true }),
    ).toBeDisabled()

    await openEditor(page, chat.name)
    const renamed = namePrefix + '_chat_edited'
    await editor(page)
      .getByLabel(/^配置名称(?:\s*此项必填)?$/)
      .fill(renamed)
    page.once('dialog', (dialog) => dialog.dismiss())
    await editor(page).getByRole('button', { name: '取消', exact: true }).click()
    await expect(editor(page).getByLabel(/^配置名称(?:\s*此项必填)?$/)).toHaveValue(renamed)
    await editor(page)
      .getByLabel(/^模型版本(?:\s*此项必填)?$/)
      .fill('2')
    await editor(page)
      .getByLabel(/^超时时间（秒）(?:\s*此项必填)?$/)
      .fill('45')
    const updated = await saveModel(page, chat.id)
    expect(updated.request.headers()['if-match']).toBe(String(chat.revision))
    expect(updated.request.postDataJSON()).not.toHaveProperty('api_key')
    chat = updated.configuration
    expect(chat).toMatchObject({
      name: renamed,
      model_version: '2',
      timeout_seconds: 45,
      has_key: true,
    })
    expectSecretHidden(await getData<AiModelConfig>(identity.api, `${configsPath}/${chat.id}`))

    await page.getByPlaceholder('按配置名称或模型标识搜索', { exact: true }).fill(renamed)
    const searched = waitForApi(page, { path: configsPath, query: { q: renamed } })
    await page.getByRole('button', { name: '搜索', exact: true }).click()
    const filtered = await responseData<AiModelPage>(await searched)
    filtered.items.forEach(expectSecretHidden)
    expect(filtered.items.map((configuration) => configuration.id)).toEqual([chat.id])
    await expect(row(page, embedding.name)).toHaveCount(0)
    await page.getByPlaceholder('按配置名称或模型标识搜索', { exact: true }).fill('')
    await page.getByRole('button', { name: '搜索', exact: true }).click()
    await expect(row(page, embedding.name)).toBeVisible()

    await openEditor(page, chat.name)
    await responseData<AiModelConfig>(
      await identity.api.put('/api/v1' + `${configsPath}/${chat.id}`, {
        headers: { 'If-Match': String(chat.revision) },
        data: { model_version: '3' },
      }),
    )
    await editor(page)
      .getByLabel(/^模型版本(?:\s*此项必填)?$/)
      .fill('4')
    evidence.allowedFailures.push({
      path: '/api/v1' + `${configsPath}/${chat.id}`,
      method: 'PUT',
      status: 409,
    })
    const conflicted = waitForApi(page, { path: `${configsPath}/${chat.id}`, method: 'PUT' })
    await editor(page).getByRole('button', { name: '保存', exact: true }).click()
    expect((await conflicted).status()).toBe(409)
    await expect(editor(page).getByRole('alert')).toContainText('已被其他操作更新')
    await expect(editor(page).getByLabel(/^模型版本(?:\s*此项必填)?$/)).toHaveValue('4')
    expect(
      (await getData<AiModelConfig>(identity.api, `${configsPath}/${chat.id}`)).model_version,
    ).toBe('3')
    page.once('dialog', (dialog) => dialog.accept())
    await editor(page).getByRole('button', { name: '重新加载配置', exact: true }).click()
    await expect(editor(page).getByLabel(/^模型版本(?:\s*此项必填)?$/)).toHaveValue('3')
    chat = (await saveModel(page, chat.id)).configuration

    chat = await enableModel(page, chat)
    embedding = await enableModel(page, embedding)
    await selectDefault(page, chat)
    await selectDefault(page, embedding)
    const selectedDefaults = await getData<AiModelDefault[]>(identity.api, defaultsPath)
    expect(selectedDefaults.find((selection) => selection.capability === 'CHAT')?.config_id).toBe(
      chat.id,
    )
    expect(
      selectedDefaults.find((selection) => selection.capability === 'EMBEDDING')?.config_id,
    ).toBe(embedding.id)
    await capture(
      page,
      info,
      evidence,
      'ai-models-defaults',
      'real ADMIN: both local model defaults',
    )

    await openEditor(page, chat.name)
    await editor(page).getByLabel('API 密钥', { exact: true }).fill('***')
    const writesBeforeMask = evidence.responses.filter(
      (entry) => entry.path === '/api/v1' + `${configsPath}/${chat.id}` && entry.method === 'PUT',
    ).length
    await editor(page).getByRole('button', { name: '保存', exact: true }).click()
    await expect(editor(page).getByRole('alert')).toContainText('星号掩码不能作为密钥')
    expect(
      evidence.responses.filter(
        (entry) => entry.path === '/api/v1' + `${configsPath}/${chat.id}` && entry.method === 'PUT',
      ).length,
    ).toBe(writesBeforeMask)
    await editor(page).getByLabel('API 密钥', { exact: true }).fill('')
    await editor(page)
      .getByLabel(/^服务地址(?:\s*此项必填)?$/)
      .fill(replacementUrl)
    await editor(page).getByRole('button', { name: '保存', exact: true }).click()
    await expect(editor(page).getByRole('alert').last()).toContainText('请重新填写密钥')
    expect((await getData<AiModelConfig>(identity.api, `${configsPath}/${chat.id}`)).base_url).toBe(
      fakeUrl,
    )
    await editor(page).getByLabel('API 密钥', { exact: true }).fill(replacementKey)
    const replaced = await saveModel(page, chat.id)
    expect(replaced.request.postDataJSON().api_key).toBe(replacementKey)
    chat = replaced.configuration
    expect(chat.base_url).toBe(replacementUrl)
    expectSecretHidden(await getData<AiModelConfig>(identity.api, `${configsPath}/${chat.id}`))

    const clearedDefault = waitForApi(page, { path: defaultsPath + '/EMBEDDING', method: 'PUT' })
    await page.getByTestId('ai-default-EMBEDDING').getByRole('button', { name: '清空默认' }).click()
    await page.getByRole('button', { name: '确认', exact: true }).last().click()
    expect((await responseData<AiModelDefault>(await clearedDefault)).config_id).toBeNull()
    await expect(page.getByTestId('ai-default-EMBEDDING')).toContainText('未配置')
    await selectDefault(page, embedding)

    const disabled = waitForApi(page, { path: `${configsPath}/${chat.id}`, method: 'PUT' })
    await row(page, chat.name).getByRole('button', { name: '停用', exact: true }).click()
    await page.getByRole('button', { name: '确认', exact: true }).last().click()
    chat = await responseData<AiModelConfig>(await disabled)
    expect(chat.enabled).toBe(false)
    await expect(page.getByTestId('ai-default-CHAT')).toContainText('未配置')
    expect(
      (await getData<AiModelDefault[]>(identity.api, defaultsPath)).find(
        (selection) => selection.capability === 'CHAT',
      )?.config_id,
    ).toBeNull()
    chat = await enableModel(page, chat)
    await selectDefault(page, chat)

    await page.setViewportSize({ width: 390, height: 844 })
    await expectNoPageOverflow(page)
    await openEditor(page, chat.name)
    await expectNoPageOverflow(page)
    await editor(page).getByRole('checkbox', { name: '清除已保存的密钥并停用配置' }).check()
    await expect(editor(page).getByRole('switch', { name: '启用配置' })).not.toBeChecked()
    await expect(editor(page).getByRole('switch', { name: '启用配置' })).toBeDisabled()
    const clearedKey = await saveModel(page, chat.id)
    expect(clearedKey.request.postDataJSON()).toMatchObject({ api_key: null, enabled: false })
    chat = clearedKey.configuration
    expect(chat).toMatchObject({
      has_key: false,
      api_key_mask: null,
      enabled: false,
      is_default: false,
    })
    await page.setViewportSize({ width: 1440, height: 960 })
    await expect(row(page, chat.name).getByText('未设置密钥', { exact: true })).toBeVisible()
    await expect(
      row(page, chat.name).getByRole('button', { name: '启用', exact: true }),
    ).toBeDisabled()
    await expect(page.getByTestId('ai-default-CHAT')).toContainText('未配置')

    const deleted = waitForApi(page, { path: `${configsPath}/${embedding.id}`, method: 'DELETE' })
    await row(page, embedding.name).getByRole('button', { name: '删除', exact: true }).click()
    await page.getByRole('button', { name: '确认', exact: true }).last().click()
    await responseData(await deleted)
    await expect(row(page, embedding.name)).toHaveCount(0)
    await expect(page.getByTestId('ai-default-EMBEDDING')).toContainText('未配置')
    const removed = await identity.api.get('/api/v1' + `${configsPath}/${embedding.id}`)
    expect(removed.status()).toBe(404)

    const deleteChat = waitForApi(page, { path: `${configsPath}/${chat.id}`, method: 'DELETE' })
    await row(page, chat.name).getByRole('button', { name: '删除', exact: true }).click()
    await page.getByRole('button', { name: '确认', exact: true }).last().click()
    await responseData(await deleteChat)
    await expect(row(page, chat.name)).toHaveCount(0)
    await settleApi(page, evidence)
    expect(
      evidence.responses.some((entry) => /\/ai\/.*(test|probe|suggest|extract)/.test(entry.path)),
    ).toBe(false)
  } finally {
    await cleanupModels(identity.api, originalDefaults, namePrefix)
  }
})

test.describe('real VIEWER cannot access model management', () => {
  test.use({ role: 'VIEWER' })
  test('route and every management API reject VIEWER credentials', async ({
    signedIn: page,
    identity,
    playwright,
    baseURL,
    evidence,
  }) => {
    const namePrefix = uniqueName('model_viewer_')
    const originalDefaults = await getData<AiModelDefault[]>(identity.api, defaultsPath)
    let viewerApi: APIRequestContext | undefined
    try {
      const configuration = await responseData<AiModelConfig>(
        await identity.api.post('/api/v1' + configsPath, {
          data: {
            name: namePrefix,
            capability: 'CHAT',
            base_url: fakeUrl,
            model: 'local-viewer-model',
            api_key: fakeKey,
          },
        }),
      )
      const tokens = await responseData<{ access_token: string }>(
        await page.request.post('/api/v1/auth/login', { data: identity.credentials.VIEWER }),
      )
      viewerApi = await playwright.request.newContext({
        baseURL,
        extraHTTPHeaders: { Authorization: 'Bearer ' + tokens.access_token },
      })
      expect((await getData<{ role: string }>(viewerApi, '/auth/me')).role).toBe('VIEWER')
      await expect(
        page.locator('.app-sider').getByRole('button', { name: 'AI 模型配置', exact: true }),
      ).toHaveCount(0)
      await page.goto('/system/ai-models')
      await expect(page).toHaveURL(/\/forbidden(?:\?|$)/)
      await expect(page.getByRole('heading', { name: '无权访问', exact: true })).toBeVisible()
      await expect(page.getByRole('button', { name: '新建模型配置', exact: true })).toHaveCount(0)
      await settleApi(page, evidence)
      expect(evidence.responses.some((entry) => entry.path.startsWith('/api/v1/ai/model-'))).toBe(
        false,
      )

      const forbiddenRequests = [
        () => viewerApi!.get('/api/v1' + configsPath),
        () => viewerApi!.get('/api/v1' + `${configsPath}/${configuration.id}`),
        () =>
          viewerApi!.post('/api/v1' + configsPath, {
            data: {
              name: namePrefix + '_forbidden',
              capability: 'CHAT',
              base_url: fakeUrl,
              model: 'local-forbidden-model',
            },
          }),
        () =>
          viewerApi!.put('/api/v1' + `${configsPath}/${configuration.id}`, {
            headers: { 'If-Match': String(configuration.revision) },
            data: { name: namePrefix + '_forbidden' },
          }),
        () =>
          viewerApi!.delete('/api/v1' + `${configsPath}/${configuration.id}`, {
            headers: { 'If-Match': String(configuration.revision) },
          }),
        () => viewerApi!.get('/api/v1' + defaultsPath),
        ...originalDefaults.map(
          (selection) => () =>
            viewerApi!.put('/api/v1' + `${defaultsPath}/${selection.capability}`, {
              headers: { 'If-Match': String(selection.revision) },
              data: { config_id: null },
            }),
        ),
      ]
      for (const request of forbiddenRequests) {
        const response = await request()
        expect(response.status()).toBe(403)
        const envelope = await response.json()
        expect(envelope.code).toBe('AUTH.FORBIDDEN')
        expect(envelope.data).toBeNull()
        expect(JSON.stringify(envelope)).not.toContain(fakeKey)
      }
      expectSecretHidden(
        await getData<AiModelConfig>(identity.api, `${configsPath}/${configuration.id}`),
      )
      expect(
        (await getData<AiModelPage>(identity.api, configsPath + '?q=' + namePrefix)).items,
      ).toHaveLength(1)
    } finally {
      try {
        await cleanupModels(identity.api, originalDefaults, namePrefix)
      } finally {
        await viewerApi?.dispose()
      }
    }
  })
})
