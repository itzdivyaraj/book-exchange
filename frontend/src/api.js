// Every call to the FastAPI backend goes through this file.
// It adds the login token, sends JSON or files, and turns server errors into readable messages.

export const API_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

const TOKEN_KEY = 'bx_token'
export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY))

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

// FastAPI errors come as {"detail": "text"} or, for 422 validation errors,
// {"detail": [{"loc": ["body", "price"], "msg": "..."}]}. Make both readable.
function readableError(detail, status) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d) => {
        const field = (d.loc || []).filter((x) => x !== 'body' && x !== 'query').join(' ')
        const msg = (d.msg || '').replace(/^Value error, /, '')
        return field ? `${field.replace(/_/g, ' ')}: ${msg}` : msg
      })
      .join(' · ')
  }
  if (status === 429) return 'Too many attempts. Please wait a bit and try again.'
  return 'Something went wrong. Please try again.'
}

/**
 * api('/books', { params: {q: 'physics'} })
 * api('/books', { method: 'POST', body: {...} })
 * api('/books/3/images', { method: 'POST', form: formData })
 */
export async function api(path, { method = 'GET', body, form, params } = {}) {
  const url = new URL(API_URL + path)
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v)
    })
  }
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let res
  try {
    res = await fetch(url, { method, headers, body: form ?? (body !== undefined ? JSON.stringify(body) : undefined) })
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your internet connection (or that the backend is running).")
  }

  if (res.status === 401 && token) {
    // Token expired or logged out elsewhere: tell the app to forget it.
    window.dispatchEvent(new Event('auth:expired'))
  }
  if (res.status === 204) return null
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, readableError(data?.detail, res.status))
  return data
}
