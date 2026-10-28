import { useEffect, useRef, useState } from 'react'
import { API_URL, LANDING_URL, analyzeIssue, checkHealth } from './api.js'
import IssueForm from './components/IssueForm.jsx'
import Result from './components/Result.jsx'
import History from './components/History.jsx'

const HISTORY_KEY = 'rca.history'
const HISTORY_LIMIT = 10
const START_COMMAND = 'cd Backend && .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000'

const STATUS_LABELS = {
  checking: 'Checking',
  online: 'Online',
  offline: 'Offline',
}

const STEPS = [
  { label: 'Describe', text: 'Say what broke, in plain words.' },
  { label: 'Match', text: 'The five closest past incidents are found and scored.' },
  { label: 'Answer', text: 'You get causes and fixes. If nothing matched closely, it says so.' },
]

// The answer currently on screen, if any, whether shown normally or held during a re-run.
function lastAnswer(view) {
  if (view.state === 'done') return view
  return view.previous ?? null
}

function loadHistory() {
  try {
    const saved = JSON.parse(localStorage.getItem(HISTORY_KEY))
    return Array.isArray(saved) ? saved : []
  } catch {
    return []
  }
}

export default function App() {
  const [apiStatus, setApiStatus] = useState('checking')
  const [issue, setIssue] = useState('')
  const [view, setView] = useState({ state: 'idle' })
  const [history, setHistory] = useState(loadHistory)
  const inFlight = useRef(null)
  const openedFromLink = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    const ping = () =>
      checkHealth(controller.signal).then((ok) => {
        if (!controller.signal.aborted) setApiStatus(ok ? 'online' : 'offline')
      })
    ping()
    const timer = setInterval(ping, 15000)
    return () => {
      controller.abort()
      clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(history))
    } catch {
      // Storage can be unavailable (private mode); history then lasts for the session only.
    }
  }, [history])

  // A link such as /?q=Redis+out+of+memory (the dashboard sends these) starts that
  // analysis straight away. The query is then dropped from the address so a refresh
  // does not run it again.
  useEffect(() => {
    if (openedFromLink.current) return
    openedFromLink.current = true
    const query = new URLSearchParams(window.location.search).get('q')?.trim()
    if (!query) return
    window.history.replaceState(null, '', window.location.pathname)
    setIssue(query)
    submit(query)
  }, [])

  async function submit(text) {
    const query = text.trim()
    if (!query) return

    inFlight.current?.abort()
    const controller = new AbortController()
    inFlight.current = controller
    // Keep the last answer on screen (dimmed) while the next one is worked out.
    setView((current) => ({ state: 'loading', issue: query, previous: lastAnswer(current) }))

    try {
      const data = await analyzeIssue(query, controller.signal)
      const entry = { id: String(Date.now()), issue: query, at: Date.now(), data }
      setApiStatus('online')
      setHistory((prev) => [entry, ...prev.filter((h) => h.issue !== query)].slice(0, HISTORY_LIMIT))
      setView({ state: 'done', id: entry.id, issue: query, data })
    } catch (err) {
      if (err.name === 'AbortError') return
      if (err.kind === 'unreachable') setApiStatus('offline')
      setView({ state: 'error', issue: query, message: err.message, unreachable: err.kind === 'unreachable' })
    }
  }

  function cancel() {
    inFlight.current?.abort()
    setView((current) => current.previous ?? { state: 'idle' })
  }

  function runExample(text) {
    setIssue(text)
    submit(text)
  }

  function openHistory(entry) {
    inFlight.current?.abort()
    setIssue(entry.issue)
    setView({ state: 'done', id: entry.id, issue: entry.issue, data: entry.data })
  }

  function clearHistory() {
    setHistory([])
  }

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href={`${LANDING_URL}/home`}>
            <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden="true">
              <rect width="32" height="32" rx="7" fill="#ffffff" />
              <path d="M16 7v7m0 0-6 9m6-9 6 9" stroke="#000000" strokeWidth="2.5" strokeLinecap="round" fill="none" />
            </svg>
            <span>déjà view</span>
          </a>
          <div className="topbar-side">
            <span className={`status status-${apiStatus}`} title={API_URL}>
              <span className="status-dot" aria-hidden="true" />
              <span>
                <span className="status-prefix">API </span>
                {STATUS_LABELS[apiStatus]}
              </span>
            </span>
            <a className="button button-ghost" href={`${LANDING_URL}/dashboard`}>
              Dashboard
            </a>
          </div>
        </div>
      </header>

      {/* Two panes: the question stays put on the left, the answer reads on the right. */}
      <main className="page">
        <div className="ask-column">
          <IssueForm
            value={issue}
            onChange={setIssue}
            onSubmit={() => submit(issue)}
            onExample={runExample}
            busy={view.state === 'loading'}
          />
          <History
            entries={history}
            activeId={view.state === 'done' ? view.id : null}
            onOpen={openHistory}
            onClear={clearHistory}
          />
        </div>

        <div className="answer-column">
          {view.state === 'idle' && apiStatus === 'offline' && (
            <Offline onRetry={() => checkHealth().then((ok) => setApiStatus(ok ? 'online' : 'offline'))} />
          )}
          {view.state === 'idle' && apiStatus !== 'offline' && <HowItWorks />}
          {view.state === 'loading' && <Loading issue={view.issue} onCancel={cancel} />}
          {view.state === 'loading' && view.previous && (
            <div className="previous" aria-hidden="true" inert>
              <Result key={view.previous.id} issue={view.previous.issue} data={view.previous.data} />
            </div>
          )}
          {view.state === 'error' && (
            <section className="panel notice" role="alert">
              <p className="label">Analysis failed</p>
              <p>{view.message}</p>
              {view.unreachable && <StartCommand />}
              <button type="button" className="button" onClick={() => submit(view.issue)}>
                Try again
              </button>
            </section>
          )}
          {view.state === 'done' && <Result key={view.id} issue={view.issue} data={view.data} />}
        </div>
      </main>
    </>
  )
}

function StartCommand() {
  return (
    <>
      <p className="muted">Start the backend from the project root, then try again:</p>
      <pre className="code">{START_COMMAND}</pre>
    </>
  )
}

function Offline({ onRetry }) {
  return (
    <section className="panel notice" role="alert">
      <p className="label">API offline</p>
      <p>
        Nothing answered at <code>{API_URL}</code>.
      </p>
      <StartCommand />
      <button type="button" className="button" onClick={onRetry}>
        Check again
      </button>
    </section>
  )
}

function HowItWorks() {
  return (
    <section className="how" aria-label="How it works">
      {STEPS.map((step, index) => (
        <div key={step.label} className="how-step">
          <p className="label">
            0{index + 1} <span className="label-rule">|</span> {step.label}
          </p>
          <p>{step.text}</p>
        </div>
      ))}
    </section>
  )
}

function Loading({ issue, onCancel }) {
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <section className="panel loading" aria-live="polite" aria-busy="true">
      <div className="loading-head">
        <p className="label">
          Analysing <span className="label-rule">|</span> {seconds}s
        </p>
        <button type="button" className="button button-ghost button-small" onClick={onCancel}>
          Cancel
        </button>
      </div>
      <p className="loading-issue">
        <span className="muted">&gt;</span> {issue}
      </p>
      <div className="progress" aria-hidden="true">
        <span />
      </div>
    </section>
  )
}
