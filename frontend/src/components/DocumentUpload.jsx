import { useState } from 'react'
import { uploadDocument } from '../api/documents'
import { ApiError, NetworkError } from '../api/client'

function DocumentUpload({ onUploadSuccess }) {
  const [selectedFile, setSelectedFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
  const [successMessage, setSuccessMessage] = useState(null)

  function handleFileChange(event) {
    setSelectedFile(event.target.files[0] ?? null)
    setError(null)
    setSuccessMessage(null)
  }

  async function handleSubmit(event) {
    event.preventDefault()

    if (!selectedFile) {
      setError('Choose a file before uploading.')
      return
    }

    setUploading(true)
    setError(null)
    setSuccessMessage(null)

    try {
      const document = await uploadDocument(selectedFile)
      setSuccessMessage(`Uploaded "${document.filename}" (${document.chunk_count} chunks).`)
      setSelectedFile(null)
      event.target.reset()
      onUploadSuccess()
    } catch (err) {
      if (err instanceof NetworkError) {
        setError(err.message)
      } else if (err instanceof ApiError) {
        setError(err.message)
      } else {
        setError('Upload failed unexpectedly.')
      }
    } finally {
      setUploading(false)
    }
  }

  return (
    <form className="upload-form" onSubmit={handleSubmit}>
      <input type="file" onChange={handleFileChange} disabled={uploading} />
      <button type="submit" disabled={uploading}>
        {uploading ? 'Uploading…' : 'Upload'}
      </button>

      {error && <p className="message message-error">{error}</p>}
      {successMessage && <p className="message message-success">{successMessage}</p>}
    </form>
  )
}

export default DocumentUpload
