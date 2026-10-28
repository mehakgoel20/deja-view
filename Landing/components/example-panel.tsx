import type { CSSProperties } from "react";

// A real answer from the analysis API, captured on 2026-10-10 for the issue below
// (engine: Backend/rag, 2,856 incidents). Shown here: the top three of its five
// matches, all three causes, and the first three of its five fixes.
const example = {
  issue: "Redis out of memory errors",
  matches: [
    { org: "yasoon", title: "Server outtage", score: 1.0 },
    { org: "Mezmo", title: "Intermittent user session timeouts, requiring periodic re-authentication", score: 0.9 },
    { org: "Gemfury", title: "Partial service failure due to non-volatile Redis saturation", score: 0.8 },
  ],
  causes: [
    "Redis instance ran out of memory due to accumulation of unremoved or excessive data such as completed jobs or session keys, leading to failure of Redis operations.",
    "Redis instance memory exhausted due to a recent configuration or deployment change that increased Redis data load or disabled automatic restarts, causing prolonged outages.",
    "Redis memory pressure caused by unexpected traffic spikes or legacy system exposure leading to excessive Redis usage.",
  ],
  fixes: [
    "Increase Redis instance memory or scale Redis cluster to handle load.",
    "Implement or fix job queue cleanup to remove completed jobs promptly.",
    "Enable automatic restart or failover for Redis to reduce downtime.",
  ],
};

const vars = (values: Record<string, number>) => values as CSSProperties;

function Label({ children }: { children: string }) {
  return <p className="text-[0.6875rem] tracking-widest text-muted uppercase">{children}</p>;
}

export function ExamplePanel() {
  return (
    <figure className="min-w-0 rounded-md border border-line bg-surface font-mono text-xs md:text-sm">
      <figcaption className="sr-only">
        Example: the analysis of the issue {example.issue}, with the three closest past incidents, three likely
        causes and three fixes.
      </figcaption>

      <div className="border-b border-line p-4 md:p-5">
        <Label>Issue</Label>
        <p className="mt-2 flex h-5 items-center gap-2">
          <span className="text-muted">&gt;</span>
          <span className="scene-type">{example.issue}</span>
          <span className="h-4 w-1.5 bg-ink" />
        </p>
      </div>

      <div className="border-b border-line p-4 md:p-5">
        <Label>Closest past incidents</Label>
        <ul className="mt-3 space-y-2.5">
          {example.matches.map((match, index) => (
            <li key={match.title} className="scene-match flex items-center gap-3" style={vars({ "--i": index })}>
              <span className="min-w-0 flex-1 truncate">
                <span className="text-muted">{match.org}</span> {match.title}
              </span>
              <span className="scene-bar h-1 w-12 shrink-0 bg-line md:w-24" style={vars({ "--score": match.score })}>
                <span />
              </span>
              <span className="tabular-nums">{match.score.toFixed(2)}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="grid gap-5 p-4 sm:grid-cols-2 md:p-5">
        <div>
          <Label>Likely causes</Label>
          <ol className="mt-3 space-y-2">
            {example.causes.map((cause, index) => (
              <li key={cause} className="scene-result flex gap-3" style={vars({ "--i": index })}>
                <span className="text-muted">{index + 1}</span>
                <span className="line-clamp-2">{cause}</span>
              </li>
            ))}
          </ol>
        </div>
        <div>
          <Label>First fixes</Label>
          <ol className="mt-3 space-y-2">
            {example.fixes.map((fix, index) => (
              <li key={fix} className="scene-result flex gap-3" style={vars({ "--i": index })}>
                <span className="text-muted">{index + 1}</span>
                <span className="line-clamp-2">{fix}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>

      <div className="scene-result border-t border-line px-4 py-3 md:px-5" style={vars({ "--i": 3 })}>
        <span className="rounded-sm bg-ink px-2 py-1 text-[0.6875rem] font-semibold tracking-widest text-paper uppercase">
          Matched past incidents
        </span>
      </div>
    </figure>
  );
}
