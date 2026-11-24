import type { TemplateInput, TemplateResource } from '@/api/templates'
import type { FormRules } from '@/components/ui/formTypes'

export type EditorMode = 'create' | 'edit' | 'copy' | 'fromOntology'
export interface EditorModel {
  metadata: TemplateInput
  ontologyId: number | null
  ontologyRevision: number | null
  resourceId: number | null
  resourceRevision: number | null
}
export interface InstanceModel {
  name: string
  iri: string
  labelZh: string
  labelEn: string
}
export interface FieldError {
  key: string
  params?: { max: number }
}
type Errors = Record<string, FieldError>
export type Translate = (key: string, params?: { max: number }) => string
const positive = (value: unknown): value is number =>
  typeof value === 'number' && Number.isSafeInteger(value) && value > 0

function textError(value: unknown, max: number, required = true): FieldError | undefined {
  if (typeof value !== 'string') return { key: 'common.required' }
  const normalized = value.trim()
  if (!normalized && required) return { key: 'common.required' }
  if (Array.from(normalized).length > max)
    return { key: 'templates.validation.maxLength', params: { max } }
}
function checkText(errors: Errors, path: string, value: unknown, max: number, required = true) {
  const error = textError(value, max, required)
  if (error) errors[path] = error
}
export function metadataPayload(input: TemplateInput) {
  return {
    name: input.name.trim(),
    source: input.source.trim(),
    basis: input.basis.trim(),
    label_i18n: Object.fromEntries(
      Object.entries(input.label_i18n)
        .filter(([, text]) => text.trim())
        .map(([key, text]) => [key, text.trim()]),
    ),
  }
}
export function instancePayload(input: InstanceModel) {
  return {
    name: input.name.trim(),
    iri: input.iri.trim(),
    label_i18n: {
      'zh-CN': input.labelZh.trim(),
      ...(input.labelEn.trim() ? { 'en-US': input.labelEn.trim() } : {}),
    },
  }
}
export function editorErrors(model: EditorModel, mode: EditorMode, adding = false): Errors {
  const errors: Errors = {}
  const input = model.metadata
  checkText(errors, 'metadata.name', input.name, 128)
  checkText(errors, 'metadata.source', input.source, 128)
  checkText(errors, 'metadata.label_i18n.zh-CN', input.label_i18n['zh-CN'], 256)
  checkText(errors, 'metadata.label_i18n.en-US', input.label_i18n['en-US'] ?? '', 256, false)
  checkText(errors, 'metadata.basis', input.basis, 4000)
  if (Object.keys(input.label_i18n).some((key) => !['zh-CN', 'en-US'].includes(key)))
    errors['metadata.label_i18n.zh-CN'] = { key: 'templates.validation.supportedLocales' }
  if (mode === 'fromOntology') {
    for (const path of ['ontologyId', 'ontologyRevision'] as const)
      if (!positive(model[path])) errors[path] = { key: 'templates.validation.positiveRevision' }
  } else if (mode !== 'copy') {
    const resources = input.resources ?? []
    if (!Array.isArray(resources) || resources.length > 1000)
      errors['metadata.resources'] = {
        key: 'templates.validation.resourcesLimit',
        params: { max: 1000 },
      }
    else if (resources.some((r) => !positive(r.resource_id) || !positive(r.pinned_revision)))
      errors['metadata.resources'] = { key: 'templates.validation.resourcePin' }
    else if (new Set(resources.map((r) => r.resource_id)).size !== resources.length)
      errors['metadata.resources'] = { key: 'templates.validation.resourcesUnique' }
    if (adding || model.resourceId !== null || model.resourceRevision !== null) {
      for (const path of ['resourceId', 'resourceRevision'] as const)
        if (!positive(model[path])) errors[path] = { key: 'templates.validation.resourcePin' }
    }
  }
  return errors
}
export function resourceSelectionError(model: EditorModel, catalog: TemplateResource[]) {
  const resource = catalog.find((item) => item.resource_id === model.resourceId)
  if (
    !positive(model.resourceId) ||
    !positive(model.resourceRevision) ||
    !resource?.revisions.includes(model.resourceRevision)
  )
    return 'templates.validation.resourcePin'
  if (model.metadata.resources?.some((item) => item.resource_id === model.resourceId))
    return 'templates.validation.resourcesUnique'
  if ((model.metadata.resources?.length ?? 0) >= 1000) return 'templates.validation.resourcesLimit'
}
export function instanceErrors(input: InstanceModel): Errors {
  const errors: Errors = {}
  checkText(errors, 'name', input.name, 128)
  checkText(errors, 'iri', input.iri, 640)
  checkText(errors, 'labelZh', input.labelZh, 256)
  checkText(errors, 'labelEn', input.labelEn, 256, false)
  return errors
}
function rulesFor(
  paths: string[],
  errors: Errors,
  current: () => Errors,
  translate: Translate,
): FormRules {
  return Object.fromEntries(
    paths.map((path) => [
      path,
      {
        message: translate(errors[path]?.key ?? 'common.required', errors[path]?.params),
        trigger: ['input', 'blur', 'change'],
        validator: () => {
          const error = current()[path]
          return error ? translate(error.key, error.params) : true
        },
      },
    ]),
  )
}
export function editorRules(
  model: EditorModel,
  mode: EditorMode,
  adding: boolean,
  translate: Translate,
  catalog: TemplateResource[],
) {
  const paths = [
    'metadata.name',
    'metadata.source',
    'metadata.label_i18n.zh-CN',
    'metadata.label_i18n.en-US',
    'metadata.basis',
  ]
  if (mode === 'fromOntology') paths.push('ontologyId', 'ontologyRevision')
  else if (mode !== 'copy') paths.push('metadata.resources', 'resourceId', 'resourceRevision')
  const current = () => {
    const errors = editorErrors(model, mode, adding)
    if (
      (mode === 'create' || mode === 'edit') &&
      (adding || model.resourceId !== null || model.resourceRevision !== null)
    ) {
      const selection = resourceSelectionError(model, catalog)
      if (selection)
        errors.resourceRevision = {
          key: selection,
          ...(selection === 'templates.validation.resourcesLimit' ? { params: { max: 1000 } } : {}),
        }
    }
    return errors
  }
  return rulesFor(paths, current(), current, translate)
}
export function instanceRules(input: InstanceModel, translate: Translate) {
  return rulesFor(
    ['name', 'iri', 'labelZh', 'labelEn'],
    instanceErrors(input),
    () => instanceErrors(input),
    translate,
  )
}
