import { useState } from 'react'

function QueryBox({ onAsk, loading }) {
  const [question, setQuestion] = useState('')
  const [validationError, setValidationError] = useState(null)

  function handleSubmit(event) {
    event.preventDefault()

    if (!question.trim()) {
      setValidationError('Enter a question before asking.')
      return
    }

    setValidationError(null)
    onAsk(question.trim())
  }

  return (
    <form className="query-form" onSubmit={handleSubmit}>
      <textarea
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        placeholder="Ask a question about your uploaded documents…"
        rows={3}
        disabled={loading}
      />
      <button type="submit" disabled={loading}>
        {loading ? 'Asking…' : 'Ask'}
      </button>

      {validationError && <p className="message message-error">{validationError}</p>}
    </form>
  )
}

export default QueryBox
