import { useCallback, useEffect, useState } from 'react'
import { listDocuments } from './api/documents'
import { askQuestion } from './api/query'
import { ApiError, NetworkError } from './api/client'
import DocumentUpload from './components/DocumentUpload'
import DocumentList from './components/DocumentList'
import QueryBox from './components/QueryBox'
import AnswerPanel from './components/AnswerPanel'

function describeError(err, fallback) {
  if (err instanceof NetworkError) return err.message
  if (err instanceof ApiError) return err.message
  return fallback
}

function App() {
  const [documents, setDocuments] = useState([])
  const [documentsLoading, setDocumentsLoading] = useState(true)
  const [documentsError, setDocumentsError] = useState(null)

  const [queryLoading, setQueryLoading] = useState(false)
  const [queryError, setQueryError] = useState(null)
  const [queryResult, setQueryResult] = useState(null)

  const fetchDocuments = useCallback(async () => {
    setDocumentsLoading(true)
    setDocumentsError(null)
    try {
      const data = await listDocuments()
      setDocuments(data)
    } catch (err) {
      setDocumentsError(describeError(err, 'Failed to load documents.'))
    } finally {
      setDocumentsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  async function handleAsk(question) {
    setQueryLoading(true)
    setQueryError(null)
    setQueryResult(null)
    try {
      const result = await askQuestion(question)
      setQueryResult(result)
    } catch (err) {
      setQueryError(describeError(err, 'Failed to get an answer.'))
    } finally {
      setQueryLoading(false)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Enterprise Knowledge Assistant</h1>
      </header>

      <main>
        <section className="panel">
          <h2>Upload a Document</h2>
          <DocumentUpload onUploadSuccess={fetchDocuments} />
          <DocumentList documents={documents} loading={documentsLoading} error={documentsError} />
        </section>

        <section className="panel">
          <h2>Ask a Question</h2>
          <QueryBox onAsk={handleAsk} loading={queryLoading} />
          {queryError && <p className="message message-error">{queryError}</p>}
          {queryResult && <AnswerPanel answer={queryResult.answer} sources={queryResult.sources} />}
        </section>
      </main>
    </div>
  )
}

export default App
