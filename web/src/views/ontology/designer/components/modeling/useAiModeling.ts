import { computed, onScopeDispose, ref, watch } from 'vue'

import type { Namespace, namespacesApi } from '@/api/namespaces'
import type {
  ModelingApplication,
  ModelingApply,
  ModelingCandidate,
  ModelingCandidateUpdate,
  ModelingCapabilities,
  ModelingCreate,
  ModelingProposal,
  ModelingValidation,
  ontologyModelingApi,
} from '@/api/ontology-modeling'

type Context = { ontologyId: number; draftId: string; baseEditRevision: number }
type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
type PendingApplication = {
  key: string
  proposalId: string
  proposalRevision: number
  payload: ModelingApply
}
type Options = {
  api: typeof ontologyModelingApi
  namespacesApi: Pick<typeof namespacesApi, 'list'>
  identity: () => string
  canWrite: () => boolean
  t: (key: string) => string
  toMessage: (cause: unknown) => string
  onApplied: (application: ModelingApplication) => void
  storage?: StorageLike | null
  makeKey?: () => string
  confirmChange?: () => boolean
  validateGenerate?: () => Promise<void>
  validateCandidate?: () => Promise<void>
}
// Only receipt identity and the confirmed apply request survive close/reopen, never source text.
const pendingReceipts = new Map<string, PendingApplication>()
export const pretty = (value: unknown) => JSON.stringify(value, null, 2) ?? ''

/** Detect duplicate keys before JSON.parse can silently discard the user's edits. */
export function parseCandidateEditor(source: string): ModelingCandidate {
  if (new TextEncoder().encode(source).length > 262144) throw new Error('candidate_too_large')
  const value: unknown = JSON.parse(source)
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('candidate_object_required')
  const stack: { keys: Set<string> | null; expectingKey: boolean }[] = []
  const tokens =
    source.match(
      /"(?:\\[\s\S]|[^"\\])*"|[{}:,]|\[|\]|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null/g,
    ) ?? []
  if (tokens.length > 80000) throw new Error('candidate_too_complex')
  for (const token of tokens) {
    const frame = stack.at(-1)
    if (token === '{' || token === '[') {
      stack.push({ keys: token === '{' ? new Set() : null, expectingKey: token === '{' })
      if (stack.length > 24) throw new Error('candidate_too_deep')
    } else if (token === '}' || token === ']') stack.pop()
    else if (token === ',' && frame?.keys) frame.expectingKey = true
    else if (token.startsWith('"') && frame?.keys && frame.expectingKey) {
      const key: string = JSON.parse(token)
      if (frame.keys.has(key)) throw new Error('candidate_duplicate_key')
      frame.keys.add(key)
      frame.expectingKey = false
    }
  }
  // The server owns strict schema/reference/semantic validation; this is the untrusted JSON boundary.
  return value as ModelingCandidate
}

export function useAiModeling(context: () => Context, options: Options) {
  const capabilities = ref<ModelingCapabilities | null>(null)
  const namespaces = ref<Namespace[]>([])
  const namespaceIds = ref<number[]>([])
  const text = ref('')
  const authorizeTransfer = ref(false)
  const excerpts = ref<{ id: string; title: string; text: string; authorized: boolean }[]>([])
  const proposals = ref<ModelingProposal[]>([])
  const total = ref(0)
  const page = ref(1)
  const validatingForm = ref(false)
  const selected = ref<ModelingProposal | null>(null)
  const candidateJson = ref('')
  const editNote = ref('')
  const validation = ref<ModelingValidation | null>(null)
  const confirmedDigest = ref('')
  const error = ref('')
  const notice = ref('')
  const initialError = ref('')
  const initializing = ref(false)
  const busy = ref<string | null>(null)
  const pendingApplication = ref<PendingApplication | null>(null)
  const application = ref<ModelingApplication | null>(null)
  let session = 0
  let operation = 0
  let listGeneration = 0
  const alive = ref(true)
  let readController: AbortController | undefined
  let generateRequest: { signature: string; key: string } | null = null
  const key = () => options.makeKey?.() ?? crypto.randomUUID()
  const receiptKey = () =>
    `kg-modeling-apply:${options.identity()}:${context().ontologyId}:${context().draftId}`
  const belongs = (proposal: ModelingProposal) =>
    proposal.ontology_id === context().ontologyId && proposal.target_draft_id === context().draftId
  const current = (ticket: { session: number; operation: number }) =>
    alive.value && ticket.session === session && ticket.operation === operation
  const dirty = computed(
    () => !!selected.value && candidateJson.value !== pretty(selected.value.candidate),
  )
  const proposalCurrent = computed(
    () =>
      !!selected.value &&
      belongs(selected.value) &&
      selected.value.base_edit_revision === context().baseEditRevision &&
      !selected.value.stale &&
      selected.value.state === 'READY',
  )
  const editable = computed(
    () =>
      alive.value &&
      options.canWrite() &&
      proposalCurrent.value &&
      !busy.value &&
      !validatingForm.value &&
      !pendingApplication.value,
  )
  const validationCurrent = computed(() => {
    const report = validation.value
    const proposal = selected.value
    return (
      !!report &&
      !!proposal &&
      proposalCurrent.value &&
      !dirty.value &&
      report.proposal_id === proposal.id &&
      report.proposal_revision === proposal.revision &&
      report.candidate_digest === proposal.candidate_digest &&
      report.can_apply &&
      report.checks.length > 0 &&
      report.checks.every(
        (check) => !check.required || check.state === 'PASS' || check.state === 'NA',
      ) &&
      report.blocking_questions.length === 0 &&
      !proposal.candidate.questions.some((question) => question.blocking)
    )
  })
  const canApply = computed(
    () =>
      editable.value &&
      validationCurrent.value &&
      !!validation.value?.compiled_plan_digest &&
      confirmedDigest.value === validation.value.compiled_plan_digest,
  )
  const generationAvailable = computed(
    () =>
      alive.value &&
      options.canWrite() &&
      capabilities.value?.chat_configured === true &&
      capabilities.value.protocol_version === 'ontology-modeling/1.0' &&
      capabilities.value.supported_profiles.includes('BUSINESS') &&
      capabilities.value.draft_only &&
      !!context().draftId &&
      !busy.value &&
      !validatingForm.value &&
      !initializing.value &&
      !pendingApplication.value,
  )
  const canGenerate = computed(
    () =>
      generationAvailable.value &&
      authorizeTransfer.value &&
      !!text.value.trim() &&
      text.value.length <= 16000 &&
      namespaceIds.value.length > 0 &&
      namespaceIds.value.length <= 20 &&
      namespaceIds.value.every((id) =>
        namespaces.value.some((ns) => ns.id === id && !ns.protected),
      ) &&
      excerpts.value.filter((excerpt) => excerpt.authorized).length <= 5 &&
      excerpts.value
        .filter((excerpt) => excerpt.authorized)
        .every(
          (excerpt) =>
            !!excerpt.title.trim() &&
            excerpt.title.length <= 200 &&
            !!excerpt.text.trim() &&
            excerpt.text.length <= 16000,
        ),
  )

  function remember(storageKey: string, pending: PendingApplication | null) {
    if (pending) pendingReceipts.set(storageKey, pending)
    else pendingReceipts.delete(storageKey)
    try {
      if (pending) options.storage?.setItem(storageKey, JSON.stringify(pending))
      else options.storage?.removeItem(storageKey)
    } catch {
      /* The in-memory receipt remains recoverable if browser storage is unavailable. */
    }
  }
  function restorePending() {
    const storageKey = receiptKey()
    const cached = pendingReceipts.get(storageKey)
    if (cached) return cached
    try {
      const raw = options.storage?.getItem(storageKey)
      if (!raw) return null
      const value = JSON.parse(raw) as PendingApplication
      if (
        typeof value.key !== 'string' ||
        !/^[A-Za-z0-9_-]{16,128}$/.test(value.key) ||
        typeof value.proposalId !== 'string' ||
        !Number.isSafeInteger(value.proposalRevision) ||
        value.payload?.target_draft_id !== context().draftId
      )
        return null
      pendingReceipts.set(storageKey, value)
      return value
    } catch {
      return null
    }
  }

  function commitProposal(proposal: ModelingProposal) {
    if (!belongs(proposal)) throw new Error('proposal_context_mismatch')
    selected.value = proposal
    candidateJson.value = pretty(proposal.candidate)
    editNote.value = ''
    validation.value = proposal.validation ?? null
    confirmedDigest.value = ''
    proposals.value = [proposal, ...proposals.value.filter((item) => item.id !== proposal.id)]
  }
  function begin(action: string) {
    error.value = ''
    notice.value = ''
    busy.value = action
    return { session, operation: ++operation }
  }
  const allowReplace = () => !dirty.value || options.confirmChange?.() === true

  // Validate the existing refs; the same session/operation still owns all writes.
  async function validateForm(
    validate: (() => Promise<void>) | undefined,
    signature: () => string,
  ) {
    if (!validate) return true
    const ticket = { session, operation }
    const before = signature()
    validatingForm.value = true
    try {
      await validate()
      return current(ticket) && before === signature()
    } catch {
      return false
    } finally {
      if (current(ticket)) validatingForm.value = false
    }
  }

  async function refreshList(nextPage = page.value) {
    if (!alive.value) return
    const generation = ++listGeneration
    const active = session
    try {
      const result = await options.api.list(context().ontologyId, nextPage, readController?.signal)
      if (!alive.value || active !== session || generation !== listGeneration) return
      proposals.value = result.items
      total.value = result.total
      page.value = nextPage
    } catch (cause) {
      if (alive.value && active === session && generation === listGeneration)
        initialError.value = options.toMessage(cause)
    }
  }
  async function initialize() {
    if (!alive.value) return
    const active = session
    readController?.abort()
    const controller = new AbortController()
    readController = controller
    initializing.value = true
    initialError.value = ''
    const results = await Promise.allSettled([
      options.api.capabilities(controller.signal),
      options.namespacesApi.list(controller.signal),
      refreshList(1),
    ])
    if (!alive.value || active !== session || controller.signal.aborted) return
    if (results[0].status === 'fulfilled') capabilities.value = results[0].value
    else initialError.value = options.toMessage(results[0].reason)
    if (results[1].status === 'fulfilled') namespaces.value = results[1].value
    else initialError.value = options.toMessage(results[1].reason)
    initializing.value = false
  }

  async function selectProposal(id: string) {
    if (
      !alive.value ||
      validatingForm.value ||
      (busy.value && busy.value !== 'select') ||
      !allowReplace()
    )
      return
    const ticket = begin('select')
    try {
      const result = await options.api.get(id)
      if (current(ticket)) commitProposal(result)
    } catch (cause) {
      if (current(ticket)) error.value = options.toMessage(cause)
    } finally {
      if (current(ticket)) busy.value = null
    }
  }
  async function generate() {
    if (!generationAvailable.value) return
    if (
      options.validateGenerate &&
      !(await validateForm(options.validateGenerate, () =>
        pretty([
          namespaceIds.value,
          text.value,
          authorizeTransfer.value,
          excerpts.value,
          candidateJson.value,
        ]),
      ))
    )
      return
    if (!canGenerate.value || !allowReplace()) return
    const target = context()
    const payload: ModelingCreate = {
      protocol_version: 'ontology-modeling/1.0',
      target_ontology_id: target.ontologyId,
      target_draft_id: target.draftId,
      base_edit_revision: target.baseEditRevision,
      profile: 'BUSINESS',
      profile_version: capabilities.value!.profile_version,
      text: text.value.trim(),
      namespace_ids: [...namespaceIds.value],
      asset_ids: [],
      excerpts: excerpts.value
        .filter((excerpt) => excerpt.authorized)
        .map((excerpt) => ({
          title: excerpt.title.trim(),
          text: excerpt.text.trim(),
          authorized: true,
        })),
      authorize_model_transfer: true,
    }
    const signature = pretty(payload)
    if (generateRequest?.signature !== signature) generateRequest = { signature, key: key() }
    const requestKey = generateRequest.key
    const ticket = begin('generate')
    try {
      const result = await options.api.create(payload, requestKey)
      if (current(ticket)) {
        commitProposal(result)
        generateRequest = null
        void refreshList(1)
      }
    } catch (cause) {
      if (current(ticket)) error.value = options.toMessage(cause)
    } finally {
      if (current(ticket)) busy.value = null
    }
  }
  async function saveCandidate() {
    if (!editable.value || !dirty.value) return
    if (
      options.validateCandidate &&
      !(await validateForm(options.validateCandidate, () =>
        pretty([selected.value?.id, selected.value?.revision, candidateJson.value, editNote.value]),
      ))
    )
      return
    if (!editable.value || !dirty.value || !editNote.value.trim() || editNote.value.length > 1000)
      return
    const proposal = selected.value!
    const source = candidateJson.value
    try {
      parseCandidateEditor(source)
    } catch {
      error.value = options.t('modeling.invalidJson')
      return
    }
    const payload: ModelingCandidateUpdate = { candidate_json: source, note: editNote.value.trim() }
    const ticket = begin('save')
    try {
      const result = await options.api.update(proposal.id, proposal.revision, payload)
      if (current(ticket) && candidateJson.value === source) commitProposal(result)
      else if (current(ticket)) {
        selected.value = result
        validation.value = null
        confirmedDigest.value = ''
      }
    } catch (cause) {
      if (current(ticket)) error.value = options.toMessage(cause)
    } finally {
      if (current(ticket)) busy.value = null
    }
  }
  async function validate() {
    if (!editable.value || dirty.value) return
    const proposal = selected.value!
    const source = candidateJson.value
    const ticket = begin('validate')
    validation.value = null
    confirmedDigest.value = ''
    try {
      const report = await options.api.validate(
        proposal.id,
        proposal.revision,
        proposal.candidate_digest,
      )
      if (
        current(ticket) &&
        candidateJson.value === source &&
        report.proposal_id === proposal.id &&
        report.proposal_revision === proposal.revision &&
        report.candidate_digest === proposal.candidate_digest
      )
        validation.value = report
    } catch (cause) {
      if (current(ticket)) error.value = options.toMessage(cause)
    } finally {
      if (current(ticket)) busy.value = null
    }
  }

  function acceptPlan(accepted: boolean) {
    confirmedDigest.value =
      accepted && validationCurrent.value ? validation.value!.compiled_plan_digest : ''
  }
  function completed(result: ModelingApplication, pending: PendingApplication, storageKey: string) {
    if (
      result.target_draft_id !== context().draftId ||
      result.proposal_id !== pending.proposalId ||
      result.proposal_revision !== pending.proposalRevision
    )
      throw new Error('application_context_mismatch')
    application.value = result
    remember(storageKey, null)
    pendingApplication.value = null
    if (selected.value?.id === result.proposal_id) selected.value.state = 'APPLIED'
    notice.value = options.t('modeling.applied')
    options.onApplied(result)
  }
  async function sendApplication(pending: PendingApplication) {
    const storageKey = receiptKey()
    const ticket = begin('apply')
    remember(storageKey, pending)
    pendingApplication.value = pending
    try {
      const result = await options.api.apply(
        pending.proposalId,
        pending.proposalRevision,
        pending.payload,
        pending.key,
      )
      if (current(ticket)) completed(result, pending, storageKey)
    } catch (cause) {
      if (!current(ticket)) return
      const failure = cause as { code?: string; status?: number }
      const definitive =
        failure.code?.startsWith('KG.') &&
        failure.code !== 'KG.ONTOLOGY_APPLICATION_OUTCOME_UNKNOWN' &&
        failure.code !== 'KG.IDEMPOTENCY_CONFLICT' &&
        failure.status !== undefined &&
        failure.status >= 400 &&
        failure.status < 500
      if (definitive) {
        remember(storageKey, null)
        pendingApplication.value = null
        error.value = options.toMessage(cause)
      } else error.value = options.t('modeling.outcomeUnknown')
    } finally {
      if (current(ticket)) busy.value = null
    }
  }
  async function apply() {
    if (!canApply.value) return
    const proposal = selected.value!
    const report = validation.value!
    const pending: PendingApplication = {
      key: key(),
      proposalId: proposal.id,
      proposalRevision: proposal.revision,
      payload: {
        protocol_version: 'ontology-modeling/1.0',
        target_draft_id: context().draftId,
        base_edit_revision: context().baseEditRevision,
        validation_report_id: report.id,
        compiled_plan_digest: report.compiled_plan_digest,
        confirmation: { accepted_plan_digest: confirmedDigest.value },
      },
    }
    await sendApplication(pending)
  }
  const canRetry = computed(
    () =>
      alive.value &&
      !!pendingApplication.value &&
      !busy.value &&
      options.canWrite() &&
      !dirty.value &&
      proposalCurrent.value &&
      selected.value?.id === pendingApplication.value.proposalId &&
      selected.value.revision === pendingApplication.value.proposalRevision &&
      context().baseEditRevision === pendingApplication.value.payload.base_edit_revision,
  )
  async function retryApplication() {
    if (canRetry.value) await sendApplication(pendingApplication.value!)
  }
  async function queryApplication() {
    const pending = pendingApplication.value
    if (!alive.value || !pending || busy.value) return
    const storageKey = receiptKey()
    const ticket = begin('query')
    try {
      const result = await options.api.applicationByKey(pending.key)
      if (!current(ticket)) return
      if (result === null) notice.value = options.t('modeling.outcomePending')
      else completed(result, pending, storageKey)
    } catch (cause) {
      if (current(ticket)) error.value = options.toMessage(cause)
    } finally {
      if (current(ticket)) busy.value = null
    }
  }
  async function discard() {
    if (!editable.value || !allowReplace()) return
    const proposal = selected.value!
    const ticket = begin('discard')
    try {
      const result = await options.api.discard(proposal.id, proposal.revision)
      if (current(ticket)) commitProposal(result)
    } catch (cause) {
      if (current(ticket)) error.value = options.toMessage(cause)
    } finally {
      if (current(ticket)) busy.value = null
    }
  }
  function addExcerpt() {
    if (alive.value && excerpts.value.length < 5)
      excerpts.value.push({ id: key(), title: '', text: '', authorized: false })
  }
  watch(
    candidateJson,
    () => {
      confirmedDigest.value = ''
    },
    { flush: 'sync' },
  )
  watch(
    () => [
      context().ontologyId,
      context().draftId,
      context().baseEditRevision,
      options.identity(),
      options.canWrite(),
    ],
    () => {
      session++
      operation++
      listGeneration++
      readController?.abort()
      busy.value = null
      validatingForm.value = false
      capabilities.value = null
      namespaces.value = []
      namespaceIds.value = []
      text.value = ''
      authorizeTransfer.value = false
      excerpts.value = []
      proposals.value = []
      total.value = 0
      selected.value = null
      candidateJson.value = ''
      editNote.value = ''
      validation.value = null
      confirmedDigest.value = ''
      error.value = ''
      notice.value = ''
      application.value = null
      generateRequest = null
      pendingApplication.value = restorePending()
      void initialize()
    },
    { immediate: true, flush: 'sync' },
  )
  function dispose() {
    alive.value = false
    session++
    operation++
    listGeneration++
    readController?.abort()
  }
  onScopeDispose(dispose)

  return {
    capabilities,
    namespaces,
    namespaceIds,
    text,
    authorizeTransfer,
    excerpts,
    proposals,
    total,
    page,
    selected,
    candidateJson,
    editNote,
    validation,
    confirmedDigest,
    error,
    notice,
    initialError,
    initializing,
    busy,
    pendingApplication,
    application,
    dirty,
    editable,
    validationCurrent,
    canGenerate,
    generationAvailable,
    validatingForm,
    canApply,
    canRetry,
    initialize,
    refreshList,
    selectProposal,
    generate,
    saveCandidate,
    validate,
    acceptPlan,
    apply,
    queryApplication,
    retryApplication,
    discard,
    addExcerpt,
    dispose,
  }
}
