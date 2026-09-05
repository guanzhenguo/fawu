const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

export interface User {
  id: number
  username: string
  name: string
  is_superuser: boolean
  roles: string[]
}

export interface Page<T> {
  count: number
  results: T[]
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('fawu_token')
  const headers = new Headers(options.headers)
  if (!(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Token ${token}`)
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (response.status === 204) return undefined as T
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || JSON.stringify(payload))
  return payload as T
}

export function rows<T>(value: Page<T> | T[]): T[] {
  return Array.isArray(value) ? value : value.results
}
