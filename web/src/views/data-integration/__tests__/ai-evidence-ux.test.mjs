import assert from 'node:assert/strict'
import { test } from 'node:test'

import { mount } from '../../../testing/view-harness.mjs'

async function sourceView(t) {
  const view = await mount(
    'views/data-integration/mapping/ai-assist/AiAssistPage.vue',
    { '@/api/ontology': { ontologyApi: { list: async () => [] } } },
    'text,ontologyId,evidenceQuote,evidenceParts,highlight,sourceInput,locateEvidence,editSource',
  )
  const unmount = view.stop
  let stopped = false
  view.stop = () => {
    if (stopped) return
    stopped = true
    unmount()
  }
  t.after(view.stop)
  return view
}

test('source highlights the first literal match and keeps the entire original text when returning to edit', async (t) => {
  const { vm } = await sourceView(t)
  const quote = '<b>原文 😀</b>'
  const source = `  Opening\n${quote}\nRepeated: ${quote}\n  `
  const focus = []
  vm.text = source
  vm.ontologyId = 1
  vm.highlight = {
    focus: () => focus.push('highlight'),
    scrollIntoView: () => focus.push('scroll'),
  }
  vm.sourceInput = { focus: () => focus.push('input') }
  await vm.locateEvidence(quote)
  assert.deepEqual(vm.evidenceParts, ['  Opening\n', quote, `\nRepeated: ${quote}\n  `])
  assert.equal(vm.evidenceParts.join(''), source)
  assert.deepEqual(focus, ['highlight', 'scroll'])
  await vm.editSource()
  assert.equal(vm.text, source)
  assert.equal(vm.evidenceParts, null)
  assert.deepEqual(focus, ['highlight', 'scroll', 'input'])
  for (const invalid of [null, '', '  ', '原文 😀', '<B>原文 😀</B>']) {
    // The plain inner text is a legal substring; case changes and whitespace-only quotes are not.
    await vm.locateEvidence(invalid)
    assert.equal(vm.evidenceQuote, invalid === '原文 😀' ? invalid : null)
  }
})

for (const change of ['text', 'ontologyId', 'unmount']) {
  test(`${change}: invalidates highlights and cancels pending focus for the old source context`, async (t) => {
    const { vm, stop } = await sourceView(t)
    vm.text = 'original quote'
    vm.ontologyId = 1
    const focus = []
    vm.highlight = {
      focus: () => focus.push('highlight'),
      scrollIntoView: () => focus.push('scroll'),
    }
    const pending = vm.locateEvidence('quote')
    if (change === 'unmount') stop()
    else if (change === 'text') vm.text = 'different source'
    else vm.ontologyId = 2
    await pending
    assert.equal(vm.evidenceParts, null)
    assert.deepEqual(focus, [])
  })
}
