// Addresses come from environment variables typed into a hosting dashboard, where the
// scheme is easy to leave off. Accept "example.com" as well as "https://example.com".
function address(value, fallback) {
  const raw = value?.trim() || fallback
  const withScheme = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`
  return withScheme.replace(/\/+$/, '')
}

// Override with VITE_API_URL in Frontend/.env.local if the backend runs elsewhere.
export const API_URL = address(import.meta.env.VITE_API_URL, 'http://127.0.0.1:8000')

// The landing site this app is reached from. Override with VITE_LANDING_URL.
export const LANDING_URL = address(import.meta.env.VITE_LANDING_URL, 'http://localhost:3000')

export class ApiError extends Error {
  constructor(kind, message) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind // 'unreachable' | 'http'
  }
}

export async function checkHealth(signal) {
  try {
    const res = await fetch(`${API_URL}/`, { signal })
    return res.ok
  } catch {
    return false
  }
}

export async function analyzeIssue(issue, signal) {
  let res
  try {
    res = await fetch(`${API_URL}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ issue }),
      signal,
    })
  } catch (err) {
    if (err.name === 'AbortError') throw err
    throw new ApiError('unreachable', `Could not reach the RCA API at ${API_URL}.`)
  }

  if (!res.ok) {
    // A 500 here usually means the OpenAI call inside the backend failed.
    const hint =
      res.status >= 500
        ? 'The backend hit an error while analysing. Check its terminal for the traceback.'
        : 'The backend rejected the request.'
    throw new ApiError('http', `${hint} (HTTP ${res.status})`)
  }
  return res.json()
}
