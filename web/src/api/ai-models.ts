import { http } from '@/api/client'
import { listPages } from '@/api/pagination'
import type { components, paths } from '@/api/schema'

type Schemas = components['schemas']
type ModelConfigRead = paths['/api/v1/ai/model-configs']['get']

export type AiModelConfig = Schemas['AiModelConfigOut']
export type AiModelCreate = Schemas['AiModelConfigCreate']
export type AiModelUpdate = Schemas['AiModelConfigUpdate']
export type AiModelDefault = Schemas['AiModelDefaultOut']
export type AiModelCapability = AiModelConfig['capability']
export type AiModelQuery = NonNullable<ModelConfigRead['parameters']['query']>
export type AiModelPage = NonNullable<
  ModelConfigRead['responses'][200]['content']['application/json']['data']
>

const base = '/ai/model-configs'
const defaultsBase = '/ai/model-defaults'
const revisionHeaders = (configuration: AiModelConfig) => ({
  'If-Match': String(configuration.revision),
})

/** Configuration writes never make a request to the configured model provider. */
export const aiModelsApi = {
  page: (params: AiModelQuery = {}, signal?: AbortSignal) =>
    http.get<AiModelPage>(base, { params, signal }).then((response) => response.data),
  list: (params: AiModelQuery = {}, signal?: AbortSignal) =>
    listPages(
      (page, page_size) =>
        aiModelsApi.page({ ...params, page, page_size }, signal).then((result) => result.items),
      signal,
      100,
    ),
  add: (payload: AiModelCreate) =>
    http.post<AiModelConfig>(base, payload).then((response) => response.data),
  edit: (configuration: AiModelConfig, payload: AiModelUpdate) =>
    http
      .put<AiModelConfig>(`${base}/${configuration.id}`, payload, {
        headers: revisionHeaders(configuration),
      })
      .then((response) => response.data),
  delete: (configuration: AiModelConfig) =>
    http
      .delete<null>(`${base}/${configuration.id}`, { headers: revisionHeaders(configuration) })
      .then((response) => response.data),
  getDetailById: (id: number, signal?: AbortSignal) =>
    http.get<AiModelConfig>(`${base}/${id}`, { signal }).then((response) => response.data),
  defaults: (signal?: AbortSignal) =>
    http.get<AiModelDefault[]>(defaultsBase, { signal }).then((response) => response.data),
  setDefault: (selection: AiModelDefault, configId: number | null) =>
    http
      .put<AiModelDefault>(
        `${defaultsBase}/${selection.capability}`,
        { config_id: configId } satisfies Schemas['AiModelDefaultUpdate'],
        { headers: { 'If-Match': String(selection.revision) } },
      )
      .then((response) => response.data),
}
