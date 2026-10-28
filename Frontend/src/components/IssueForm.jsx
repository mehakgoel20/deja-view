import { useEffect, useRef } from 'react'

const EXAMPLES = [
  'Kubernetes pod stuck in CrashLoopBackOff',
  'Redis out of memory errors',
  'High number of 5xx errors after code release',
  'Checkout API returns 502 after the last deploy',
]

// Looks and behaves like the ask box on the dashboard (Landing/app/dashboard/page.tsx):
// Enter sends, Shift+Enter starts a new line.
export default function IssueForm({ value, onChange, onSubmit, onExample, busy }) {
  const canSubmit = value.trim().length > 0 && !busy
  const field = useRef(null)

  // Grow the field with its content instead of scrolling inside it.
  useEffect(() => {
    const el = field.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [value])

  function handleSubmit(event) {
    event.preventDefault()
    if (!canSubmit) return
    // Sending with Enter leaves the caret in the field; let go of it so the
    // highlight goes away while the answer is shown.
    field.current?.blur()
    onSubmit()
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) handleSubmit(event)
  }

  return (
    <form className="panel issue-form" onSubmit={handleSubmit}>
      <div className="ask">
        <h1 className="label">
          <label htmlFor="issue">What is going wrong?</label>
        </h1>
        <div className="ask-row">
          <div className="field">
            <span className="field-prompt" aria-hidden="true">
              &gt;
            </span>
            <textarea
              id="issue"
              ref={field}
              rows={3}
              value={value}
              onChange={(event) => onChange(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Describe the issue in plain words"
            />
          </div>
          <button type="submit" className="button" disabled={!canSubmit}>
            {busy ? 'Analysing' : 'Analyse'}
          </button>
        </div>
      </div>
      <div className="examples">
        <span className="label">Try</span>
        {EXAMPLES.map((example) => (
          <button key={example} type="button" className="chip" onClick={() => onExample(example)} disabled={busy}>
            {example}
          </button>
        ))}
      </div>
    </form>
  )
}
