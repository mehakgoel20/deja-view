const MODE_TAGS = { RAG: 'Matched', LLM_ONLY: 'Model only' }

function timeAgo(timestamp) {
  const minutes = Math.floor((Date.now() - timestamp) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  return new Date(timestamp).toLocaleDateString()
}

export default function History({ entries, activeId, onOpen, onClear }) {
  return (
    <section className="panel history">
      <div className="history-head">
        <h2 className="label">Recent</h2>
        {entries.length > 0 && (
          <button type="button" className="link" onClick={onClear}>
            Clear
          </button>
        )}
      </div>

      {entries.length === 0 ? (
        <p className="muted">Your last 10 analyses appear here. They stay in this browser.</p>
      ) : (
        <ul>
          {entries.map((entry) => (
            <li key={entry.id}>
              <button
                type="button"
                className={`history-item${entry.id === activeId ? ' is-active' : ''}`}
                onClick={() => onOpen(entry)}
              >
                <span className="history-issue">{entry.issue}</span>
                <span className="history-meta">
                  {MODE_TAGS[entry.data?.mode] ?? entry.data?.mode} <span className="label-rule">|</span> {timeAgo(entry.at)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
