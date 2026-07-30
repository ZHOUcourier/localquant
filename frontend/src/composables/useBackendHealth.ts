import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'

/**
 * 全局后端健康检查
 * 每 5 秒轮询 /api/health，后端不可达时 online=false，
 * 用于在界面上给出"后端未启动"的清晰提示。
 */
export function useBackendHealth() {
  const { data, isError, isLoading } = useQuery({
    queryKey: ['backend-health'],
    queryFn: async () => {
      const res = await fetch('/api/health')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.json() as Promise<{ status: string; version: string }>
    },
    refetchInterval: 5000,
    retry: false,
    refetchOnWindowFocus: true,
  })

  return {
    online: computed(() => !isError.value && data.value?.status === 'ok'),
    checking: isLoading,
    version: computed(() => data.value?.version),
  }
}
