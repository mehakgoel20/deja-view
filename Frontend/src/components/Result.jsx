import { useMemo, useState } from 'react'
import { normalizeResponse, toPlainText } from '../parse.js'

const MODES = {
  RAG: {
    label: 'Matched past incidents',
    solid: true,
    blurb: 'Based on similar past incidents, listed below.',
  },
  LLM_ONLY: {
    label: 'Model reasoning only',
    solid: false,
    blurb: 'No close match on record. This is the model’s general reasoning, so treat it as a starting point.',
  },
}

export default function Result({ issue, data }) {
  const result = useMemo(() => normalizeResponse(data), [data])
  const mode = MODES[result.mode] ?? { label: result.mode, solid: false, blurb: '' }
  const hasAnalysis = result.rootCauses.length > 0 || result.solutions.length > 0
  const scores = result.similar.map((item) => item.score).filter((score) => score !== null)
  const topScore = scores.length ? Math.max(...scores) : null
  const percent = result.confidence === null ? null : Math.round(result.confidence * 100)

  return (
    <section className="panel result" aria-live="polite">
      <header className="result-head">
        <div>
          <p className="label">Analysis</p>
          <h2>{issue}</h2>
        </div>
        <CopyButton text={toPlainText(issue, result)} />
      </header>

      <div className="source">
        <span className={`badge${mode.solid ? ' badge-solid' : ''}`}>{mode.label}</span>
        {mode.blurb && <p>{mode.blurb}</p>}
      </div>

      {result.rawOutput && (
        <div className="result-block notice">
          <p className="label">Unformatted reply</p>
          <p className="muted">The model’s reply could not be read as structured data. This is what it returned:</p>
          <pre className="code">{result.rawOutput}</pre>
        </div>
      )}

      {hasAnalysis && (
        <dl className="stats">
          <Stat
            label="Model confidence"
            value={percent === null ? 'n/a' : `${percent}%`}
            note="Reported by the model itself"
            meter={percent}
          />
          <Stat
            label="Closest match"
            value={topScore === null ? 'None' : topScore.toFixed(2)}
            note={topScore === null ? 'Nothing close enough on record' : 'Relevance, from 0 to 1'}
            meter={topScore === null ? null : Math.round(topScore * 100)}
          />
          <Stat
            label="Past incidents used"
            value={String(result.similar.length)}
            note={result.similar.length ? 'Listed below' : 'The answer has no past case behind it'}
          />
        </dl>
      )}

      {hasAnalysis && (
        <div className="findings">
          <Findings title="Likely causes" items={result.rootCauses} />
          <Findings title="Fixes" items={result.solutions} />
        </div>
      )}

      {result.explanation && (
        <div className="result-block">
          <p className="label">Why</p>
          <p className="why">{result.explanation}</p>
        </div>
      )}

      {result.similar.length > 0 && (
        <div className="result-block">
          <p className="label">Closest past incidents</p>
          <ul className="similar">
            {result.similar.map((item, index) => (
              <SimilarIssue key={`${item.title}-${index}`} item={item} open={index === 0} />
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

function Stat({ label, value, note, meter = null }) {
  return (
    <div className="stat">
      <dt className="label">{label}</dt>
      <dd>
        <span className="stat-value">{value}</span>
        {meter !== null && (
          <span className="meter" aria-hidden="true">
            <span style={{ width: `${meter}%` }} />
          </span>
        )}
        <span className="stat-note">{note}</span>
      </dd>
    </div>
  )
}

function Findings({ title, items }) {
  return (
    <div className="findings-col">
      <p className="label">{title}</p>
      {items.length === 0 ? (
        <p className="muted">None returned.</p>
      ) : (
        <ol>
          {items.map((item, index) => (
            <li key={index}>
              <span className="num">{index + 1}</span>
              <span>{item}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function SimilarIssue({ item, open }) {
  return (
    <li className="similar-item">
      <details open={open}>
        <summary>
          <span className="similar-title">{item.title}</span>
          {item.score !== null && (
            <span className="score" title="Relevance to your description, from 0 to 1">
              <span className="meter meter-small" aria-hidden="true">
                <span style={{ width: `${Math.round(item.score * 100)}%` }} />
              </span>
              {item.score.toFixed(2)}
            </span>
          )}
        </summary>
        <div className="similar-body">
          <SimilarList title="Recorded cause" items={item.causes} />
          <SimilarList title="Recorded fix" items={item.solutions} />
        </div>
      </details>
    </li>
  )
}

function SimilarList({ title, items }) {
  if (items.length === 0) return null
  return (
    <div>
      <p className="label">{title}</p>
      <ul>
        {items.map((entry, index) => (
          <li key={index}>{entry}</li>
        ))}
      </ul>
    </div>
  )
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }

  return (
    <button type="button" className="button button-ghost button-small" onClick={copy}>
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}
