import { computed } from 'vue'

import { useAuthStore } from '@/stores/auth'

export function useGovernanceAccess() {
  const auth = useAuthStore()
  const canWrite = computed(() => auth.user?.role === 'ADMIN' || auth.user?.role === 'EDITOR')
  return { canWrite }
}
