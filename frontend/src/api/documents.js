import { apiFetch } from './client'

/** GET /api/documents -> Document[] */
export function listDocuments() {
  return apiFetch('/api/documents')
}

/** POST /api/documents/upload (multipart) -> Document */
export function uploadDocument(file) {
  const formData = new FormData()
  formData.append('file', file)

  return apiFetch('/api/documents/upload', {
    method: 'POST',
    body: formData,
  })
}
