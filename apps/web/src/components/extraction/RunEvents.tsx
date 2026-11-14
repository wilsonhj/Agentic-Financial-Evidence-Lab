"use client";
import { useEffect, useRef, useState } from "react";
import type { Event } from "../../lib/extraction/contracts";
import { consumeExtractionEvents } from "../../lib/extraction/sse";
import { Timestamp } from "./labels";

export function RunEvents({ runId }: { runId: string }) {
  const [events, setEvents] = useState<Event[]>([]);
  const [status, setStatus] = useState("Connecting");
  const [attempt, setAttempt] = useState(0);
  const lastId = useRef(0);
  useEffect(() => {
    const controller = new AbortController();
    void consumeExtractionEvents(runId, {
      signal: controller.signal,
      lastId: lastId.current,
      onEvent(event) {
        lastId.current = event.id;
        if (event.type !== "heartbeat") {
          setEvents((previous) => [...previous, event].slice(-500));
          setStatus(event.type);
        }
      },
      onStatus: setStatus,
    }).catch(() => {
      if (!controller.signal.aborted)
        setStatus("Stream disconnected. Reconnect explicitly to resume from the last event.");
    });
    return () => controller.abort();
  }, [runId, attempt]);
  return (
    <section aria-label="Live extraction events" className="extraction-card">
      <h2>Live events</h2>
      <div className="extraction-toolbar">
        <p role="status" aria-live="polite" className="extraction-live">
          {status}
        </p>
        <button
          type="button"
          className="extraction-button"
          onClick={() => setAttempt((a) => a + 1)}
        >
          Reconnect live events
        </button>
      </div>
      <p className="extraction-hint">
        Retains the newest 500 events in this view. Waiting for review keeps the stream open.
      </p>
      <div
        className="extraction-table-scroll"
        role="region"
        aria-label="Ordered event history, scrollable"
        tabIndex={0}
      >
        <table className="extraction-table">
          <caption>Ordered event history</caption>
          <thead>
            <tr>
              <th scope="col" className="extraction-num">
                Event ID
              </th>
              <th scope="col">Event</th>
              <th scope="col">Time</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id}>
                <td className="extraction-num">{e.id}</td>
                <td className="extraction-mono">{e.type}</td>
                <td className="extraction-nowrap">
                  <Timestamp value={e.occurred_at} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
