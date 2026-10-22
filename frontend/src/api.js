// Minimal API client for the JobRix Django backend (token auth).
//
// * Base URL comes from VITE_API_URL (default: local runserver).
// * The DRF token lives in localStorage (see auth.jsx) and is attached to
//   every request as `Authorization: Token <key>`.
// * Every non-2xx response throws ApiError carrying the parsed body, so pages
//   can show the backend's own validation messages (e.g. 409 conflicts).

const BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

export class ApiError extends Error {
  constructor(status, data) {
    super(extractDetail(data) || `Request failed (${status})`)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

function extractDetail(data) {
  if (!data || typeof data !== 'object') return typeof data === 'string' ? data : ''
  if (typeof data.detail === 'string') return data.detail
  // Field errors: {field: ["msg", ...]} -> "field: msg"
  return Object.entries(data)
    .map(([field, msgs]) => `${field}: ${(msgs || []).join(' ')}`)
    .join(' · ')
}

async function request(path, { method = 'GET', body, rawBody } = {}) {
  const headers = {}
  const token = localStorage.getItem('jobrix_token')
  if (token) headers.Authorization = `Token ${token}`
  if (body) headers['Content-Type'] = 'application/json'

  // DRF hands back absolute URLs for the next page - pass those through as-is.
  const url = /^https?:\/\//.test(path) ? path : `${BASE}${path}`

  let response
  try {
    response = await fetch(url, {
      method,
      headers,
      body: rawBody || (body ? JSON.stringify(body) : undefined),
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the API. Is the backend running on ' + BASE + '?')
  }

  const isJson = (response.headers.get('content-type') || '').includes('json')
  const data = isJson ? await response.json() : await response.text()
  if (!response.ok) throw new ApiError(response.status, data)
  return data
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body }),
  patch: (path, body) => request(path, { method: 'PATCH', body }),
  delete: (path) => request(path, { method: 'DELETE' }),
  upload: (path, formData) => request(path, { method: 'POST', rawBody: formData }),
}

// List responses are paginated ({count, results}) -> always hand back rows.
export function rows(payload) {
  if (Array.isArray(payload)) return payload
  return (payload && payload.results) || []
}

// Fetch *every* page of a paginated list and return the same {count, results}
// shape, so a list can never silently show only the first PAGE_SIZE (20) rows.
// DRF returns an absolute `next` URL, which `request` passes through as-is.
export async function getAll(path) {
  let url = path
  const results = []
  let count = 0
  let guard = 0

  while (url && guard < 50) {
    guard += 1
    const data = await request(url)
    if (Array.isArray(data)) return { count: data.length, results: data }
    results.push(...(data.results || []))
    count = data.count ?? results.length
    url = data.next || null
  }
  return { count, results }
}

export function fileUrl(path) {
  return `${BASE}${path}`
}
