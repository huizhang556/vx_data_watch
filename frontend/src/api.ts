let csrfToken = ''

export function setCsrfToken(value?: string) {
  csrfToken = value || ''
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const method = (init.method || 'GET').toUpperCase()
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) headers.set('X-CSRF-Token', csrfToken)
  const response = await fetch(path, { ...init, headers, credentials: 'same-origin' })
  if (!response.ok) {
    if (response.status === 401 && typeof window !== 'undefined') window.dispatchEvent(new Event('vx:unauthorized'))
    let detail = response.status === 413
      ? '上传失败：服务器拒绝了请求，截图文件或本次上传总大小超过限制。请压缩图片、减少一次上传数量后重试。'
      : `请求失败 (${response.status})`
    const raw = await response.text()
    if (raw.trim()) {
      try {
        const body = JSON.parse(raw) as { detail?: unknown }
        if (typeof body.detail === 'string') detail = body.detail
        else if (body.detail !== undefined) detail = JSON.stringify(body.detail)
      } catch {
        if (response.status !== 413) detail = `${detail}：${raw.slice(0, 240)}`
      }
    }
    throw new Error(detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function query(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => value !== undefined && search.set(key, String(value)))
  return search.toString()
}
