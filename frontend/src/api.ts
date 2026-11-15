const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  })
  const payload = await response.json()
  if (!response.ok || payload.error_code) throw new Error(payload.detail ?? payload.message ?? '请求失败')
  return payload.data as T
}

