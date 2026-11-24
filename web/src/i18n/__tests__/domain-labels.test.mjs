import assert from 'node:assert/strict'
import { test } from 'node:test'

import { mount, settle } from '../../testing/view-harness.mjs'

const labels = { 'zh-CN': '员工', 'en-US': '   ' }
const ontology = {
  id: 9,
  name: 'EmployeeModel',
  iri: 'urn:example:model',
  label_i18n: labels,
  current_revision: 3,
}

test('real mapping options mark missing labels without changing selected identity or draft fields', async (t) => {
  const ctx = await mount(
    'views/data-integration/mapping/MappingWorkbenchPage.vue',
    {
      '@/api/mappings': { mappingsApi: { list: async () => [] } },
      '@/api/datasources': { datasourcesApi: { list: async () => [] }, metadataApi: {} },
      '@/api/ontology': { ontologyApi: { list: async () => [ontology], refs: async () => [] } },
      '@/api/entity-types': { entityTypesApi: { list: async () => [] } },
      '@/api/relations': { relationsApi: { list: async () => [] } },
    },
    'entityTypes,relationTypes,entityOptions,relationOptions,ontologyOption,selectedOntologyId,resourceLabel,locale,mappingName',
  )
  t.after(ctx.stop)
  ctx.vm.entityTypes = [{ name: 'Employee', label_i18n: labels }]
  ctx.vm.relationTypes = [{ name: 'WorksIn', label_i18n: { 'zh-CN': '就职于' } }]
  ctx.vm.selectedOntologyId = 9
  ctx.vm.mappingName = 'DraftName'
  assert.deepEqual(ctx.vm.entityOptions, [
    { value: 'Employee', label: 'Employee (Not translated)' },
  ])
  assert.deepEqual(ctx.vm.relationOptions, [
    { value: 'WorksIn', label: 'WorksIn (Not translated)' },
  ])
  assert.equal(ctx.vm.ontologyOption(ontology).value, 9)
  assert.match(ctx.vm.ontologyOption(ontology).label, /Not translated/)
  ctx.vm.entityTypes[0].label_i18n['en-US'] = 'Employee label'
  await settle()
  assert.equal(ctx.vm.entityOptions[0].label, 'Employee label')
  ctx.vm.locale = 'zh-CN'
  await settle()
  assert.equal(ctx.vm.entityOptions[0].label, '员工')
  assert.equal(ctx.vm.relationOptions[0].label, '就职于')
  assert.equal(ctx.vm.ontologyOption(ontology).label, '员工 · EmployeeModel')
  assert.equal(ctx.vm.selectedOntologyId, 9)
  assert.equal(ctx.vm.mappingName, 'DraftName')
})

test('real export options mark blank translations and retain frozen revision selection on locale changes', async (t) => {
  const ctx = await mount(
    'views/governance/exchange/OntologyExchangePage.vue',
    {
      '@/api/ontology': { ontologyApi: { list: async () => [ontology] } },
    },
    'ontologies,options,selectedId,revision,locale',
  )
  t.after(ctx.stop)
  ctx.vm.ontologies = [{ ...ontology, label_i18n: { 'zh-CN': '员工模型', 'en-US': ' ' } }]
  ctx.vm.selectedId = 9
  ctx.vm.revision = 2
  assert.deepEqual(ctx.vm.options[0], {
    value: 9,
    label: 'Not translated · EmployeeModel',
    disabled: false,
  })
  ctx.vm.locale = 'zh-CN'
  await settle()
  assert.equal(ctx.vm.options[0].label, '员工模型 · EmployeeModel')
  assert.equal(ctx.vm.selectedId, 9)
  assert.equal(ctx.vm.revision, 2)
  ctx.vm.ontologies[0].label_i18n['en-US'] = 'Employee model'
  ctx.vm.locale = 'en-US'
  await settle()
  assert.equal(ctx.vm.options[0].label, 'Employee model · EmployeeModel')
  assert.equal(ctx.vm.selectedId, 9)
  assert.equal(ctx.vm.revision, 2)
})
