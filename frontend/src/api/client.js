const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

if (!API_BASE_URL) {
  // Fail loudly at startup rather than silently hitting a wrong/relative URL.
  throw new Error(
    'VITE_API_BASE_URL is not set. Copy .env.example to .env and set it to your backend URL.'
  )
}

/** Thrown for any response the server actually sent back (4xx/5xx). */
export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Thrown when the request never reached the server (offline, wrong port, CORS, etc). */
export class NetworkError extends Error {
  constructor(message) {
    super(message)
    this.name = 'NetworkError'
  }
}

/**
 * Extracts a human-readable message from a DRF error body, which may be
 * {"detail": "..."} or a serializer validation error like {"question": ["..."]}.
 */
function extractErrorMessage(body, fallback) {
  if (!body || typeof body !== 'object') return fallback
  if (typeof body.detail === 'string') return body.detail

  const firstField = Object.values(body)[0]
  if (Array.isArray(firstField) && typeof firstField[0] === 'string') {
    return firstField[0]
  }

  return fallback
}

/**
 * Thin fetch wrapper: joins the base URL, parses JSON, and turns failures
 * into ApiError (server responded) or NetworkError (request never landed)
 * so callers can tell the two apart.
 */
export async function apiFetch(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, options)
  } catch {
    throw new NetworkError(
      'Could not reach the backend. Check that the API server is running.'
    )
  }

  const isJson = response.headers.get('content-type')?.includes('application/json')
  const body = isJson ? await response.json().catch(() => null) : null

  if (!response.ok) {
    throw new ApiError(
      extractErrorMessage(body, `Request failed with status ${response.status}.`),
      response.status
    )
  }

  return body
}
