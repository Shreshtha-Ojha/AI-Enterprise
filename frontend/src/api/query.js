import { apiFetch } from './client'

/** POST /api/query {question} -> {answer, sources: [{document, chunk_id}]} */
export function askQuestion(question) {
  return apiFetch('/api/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
}
