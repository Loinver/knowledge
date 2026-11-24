import type { DatasourceCreate, DatasourceUpdate, TestConnectionRequest } from '@/api/datasources'
import type { FormRules } from '@/components/ui/formTypes'

export interface SourceForm {
  name: string
  kind: 'sqlite' | 'mysql' | 'postgresql'
  database: string
  host: string
  port: number | null
  user: string
  credential: string
}

export function emptySourceForm(): SourceForm {
  return { name: '', kind: 'sqlite', database: '', host: '', port: null, user: '', credential: '' }
}

export function connectionInput(form: SourceForm): TestConnectionRequest {
  const params =
    form.kind === 'sqlite'
      ? { database: form.database.trim() }
      : {
          host: form.host.trim(),
          port: form.port ?? (form.kind === 'mysql' ? 3306 : 5432),
          database: form.database.trim(),
          user: form.user.trim(),
        }
  return {
    kind: form.kind,
    params,
    ...(form.credential ? { credential: form.credential } : {}),
  }
}

export function createInput(form: SourceForm): DatasourceCreate {
  return { name: form.name.trim(), ...connectionInput(form) }
}

export function editInput(form: { name: string; credential: string }): DatasourceUpdate {
  // Empty means keep the stored secret. Never send masked connection parameters.
  return { name: form.name.trim(), ...(form.credential ? { credential: form.credential } : {}) }
}

export function sourceRules(
  network: boolean,
  messages: { name: string; connection: string; required: string },
): FormRules {
  return {
    name: { required: true, message: messages.name, trigger: ['input', 'blur'] },
    kind: { required: true, message: messages.required, trigger: 'change' },
    database: { required: true, message: messages.connection, trigger: ['input', 'blur'] },
    ...(network
      ? {
          host: { required: true, message: messages.connection, trigger: ['input', 'blur'] },
          user: { required: true, message: messages.connection, trigger: ['input', 'blur'] },
        }
      : {}),
  }
}
