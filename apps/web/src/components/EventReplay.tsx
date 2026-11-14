import { formatUtc, humanizeCode } from "../lib/observatory/labels";
import type { RetrievalTrace } from "../lib/observatory/query-source";

type StoredEvent = RetrievalTrace["events"][number];

/** Ordered list of persisted retrieval events, shared by the replay and the history page. */
export function EventList({ events }: { events: readonly StoredEvent[] }) {
  return (
    <ol className="obs-replay">
      {events.map((event) => (
        <li key={event.seq}>
          <span className="badge badge-info">#{event.seq}</span>{" "}
          <span title={event.type}>{humanizeCode(event.type)}</span>{" "}
          <time className="obs-muted" dateTime={event.occurred_at} title={event.occurred_at}>
            {formatUtc(event.occurred_at)}
          </time>
        </li>
      ))}
    </ol>
  );
}

/**
 * Stored replay of a run's persisted event log. This is a read of the trace's
 * events (no new run is created), rendered in seq order so the run can be
 * stepped through after the fact. Collapsed by default: it is raw detail.
 */
export function EventReplay({ trace }: { trace: RetrievalTrace }) {
  const events = [...trace.events].sort((a, b) => a.seq - b.seq);
  return (
    <section
      id="obs-replay"
      className="panel-card obs-section"
      aria-labelledby="obs-replay-heading"
    >
      <h2 id="obs-replay-heading">Stored replay</h2>
      {events.length === 0 ? (
        <p className="obs-empty">No persisted events for this run.</p>
      ) : (
        <details className="obs-details">
          <summary>
            Show {events.length} recorded event{events.length === 1 ? "" : "s"}
          </summary>
          <EventList events={events} />
        </details>
      )}
    </section>
  );
}
