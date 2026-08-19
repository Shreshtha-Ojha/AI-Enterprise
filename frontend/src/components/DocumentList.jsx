function formatUploadedAt(isoString) {
  return new Date(isoString).toLocaleString()
}

function DocumentList({ documents, loading, error }) {
  if (loading) {
    return <p className="hint">Loading documents…</p>
  }

  if (error) {
    return <p className="message message-error">{error}</p>
  }

  if (documents.length === 0) {
    return <p className="hint">No documents uploaded yet.</p>
  }

  return (
    <ul className="document-list">
      {documents.map((document) => (
        <li key={document.id} className="document-list-item">
          <span className="document-name">{document.filename}</span>
          <span className={`status-badge status-${document.status}`}>{document.status}</span>
          <span className="document-meta">
            {document.chunk_count} chunks · {formatUploadedAt(document.uploaded_at)}
          </span>
          {document.status === 'failed' && document.error_message && (
            <span className="message message-error">{document.error_message}</span>
          )}
        </li>
      ))}
    </ul>
  )
}

export default DocumentList
