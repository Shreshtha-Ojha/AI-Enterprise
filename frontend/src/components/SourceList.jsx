function SourceList({ sources }) {
  if (sources.length === 0) {
    return <p className="hint">No relevant sources were found for this answer.</p>
  }

  return (
    <ul className="source-list">
      {sources.map((source, index) => (
        <li key={`${source.document}-${source.chunk_id}-${index}`} className="source-list-item">
          <span className="document-name">{source.document}</span>
          <span className="document-meta">chunk: {source.chunk_id}</span>
        </li>
      ))}
    </ul>
  )
}

export default SourceList
