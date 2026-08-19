import SourceList from './SourceList'

function AnswerPanel({ answer, sources }) {
  return (
    <div className="answer-panel">
      <p className="answer-text">{answer}</p>
      <h3>Sources</h3>
      <SourceList sources={sources} />
    </div>
  )
}

export default AnswerPanel
