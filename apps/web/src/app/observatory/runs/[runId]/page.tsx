import { PageNavigation } from "../../../../components/PageNavigation";
import { EvidenceContractError } from "../../../../lib/data/http-source";
import Link from "next/link";

import { EvidenceFailureState } from "../../../../components/EvidenceFailureState";
import { EventReplay } from "../../../../components/EventReplay";
import { FeedbackControl } from "../../../../components/FeedbackControl";
import {
  ObservatoryTrace,
  RunSectionNav,
  TRACE_SECTIONS,
  type RunSection,
} from "../../../../components/ObservatoryTrace";
import { RerunButton } from "../../../../components/RerunButton";
import { getEvidenceSource } from "../../../../lib/data/server";
import { observatoryFailureState } from "../../../../lib/observatory/errors";
import { sanitizeObservatoryError } from "../../../../lib/observatory/known-errors";
import {
  candidateLabel,
  formatUtc,
  humanizeCode,
  shortId,
} from "../../../../lib/observatory/labels";
import type { QueryPage } from "../../../../lib/observatory/query-source";
import { buildDocumentIdByVersionId } from "../../../../lib/observatory/reader-links";
import { getObservatorySource } from "../../../../lib/observatory/server";
import { LANE_LABELS, partitionCandidates } from "../../../../lib/observatory/trace-view";

export const dynamic = "force-dynamic";

export default async function ObservatoryRunPage({
  params,
  searchParams,
}: {
  params: Promise<{ runId: string }>;
  searchParams?: Promise<{
    error?: string;
    feedback?: string;
    cursor?: string;
    order?: "asc" | "desc";
  }>;
}) {
  const { runId } = await params;
  const { error, feedback, cursor, order } = (await searchParams) ?? {};
  const safeError = sanitizeObservatoryError(error);
  const source = getObservatorySource();

  let trace;
  try {
    trace = await source.getRun(runId);
  } catch (caught) {
    const kind = observatoryFailureState(caught);
    if (kind)
      return (
        <>
          <EvidenceFailureState kind={kind} />
          <p>
            <Link href={`/observatory/runs/${encodeURIComponent(runId)}/history`}>
              Inspect event history
            </Link>
          </p>
        </>
      );
    throw caught;
  }

  // Keep immutable query metadata alongside one explicitly bounded run-history page.
  let snapshot: QueryPage | undefined;
  try {
    snapshot = await source.getQuery(trace.query_id, { limit: 50, cursor, order: order ?? "asc" });
  } catch (caught) {
    const kind = observatoryFailureState(caught);
    if (kind) return <EvidenceFailureState kind={kind} />;
    throw caught;
  }

  // Reader deep links are best-effort: an unavailable evidence source disables
  // candidate links rather than failing the whole trace view.
  let documentIdByVersionId: Record<string, string>;
  try {
    documentIdByVersionId = await buildDocumentIdByVersionId(
      getEvidenceSource(),
      trace.candidates.map((candidate) => candidate.document_version_id),
      { asOf: trace.plan.effective_as_of, corpusVersionId: trace.plan.corpus_version_id },
    );
  } catch (caught) {
    if (caught instanceof EvidenceContractError) return <EvidenceFailureState kind="integrity" />;
    documentIdByVersionId = {};
  }

  const compareWith = snapshot?.runs.find((run) => run.run_id !== runId);
  const { rejected } = partitionCandidates(trace);
  const rejectionCode = new Map(rejected.map(({ candidate, code }) => [candidate.item_id, code]));
  const sections: RunSection[] = [
    ...TRACE_SECTIONS,
    { id: "obs-feedback", label: "Evidence feedback" },
    ...(snapshot ? [{ id: "obs-history", label: "Run history" }] : []),
    { id: "obs-replay", label: "Stored replay" },
  ];

  return (
    <main id="main-content" tabIndex={-1} className="page-main obs-run-page">
      <p>
        <Link href="/observatory">← Search Observatory</Link>
      </p>
      <h1>Retrieval run</h1>

      {safeError && (
        <p className="reader-banner citation-error" role="alert">
          Action failed: {safeError}
        </p>
      )}
      {feedback === "recorded" && (
        <p className="reader-banner" role="status">
          Feedback recorded.
        </p>
      )}

      <div className="obs-run-layout">
        <RunSectionNav sections={sections} />
        <div className="obs-run-content">
          <div className="obs-actions">
            <RerunButton queryId={trace.query_id} runId={runId} />
            {compareWith && (
              <Link
                className="retry-button"
                href={`/observatory/compare?a=${runId}&b=${compareWith.run_id}`}
                title={compareWith.run_id}
              >
                Compare with run {shortId(compareWith.run_id)} ({humanizeCode(compareWith.mode)})
              </Link>
            )}
          </div>

          <ObservatoryTrace
            trace={trace}
            snapshot={snapshot}
            documentIdByVersionId={documentIdByVersionId}
          />

          <section
            id="obs-feedback"
            className="panel-card obs-section"
            aria-labelledby="obs-feedback-heading"
          >
            <h2 id="obs-feedback-heading">Evidence feedback</h2>
            <p className="obs-muted">
              One row per retrieved candidate, identified by its fused rank and lane ranks.
            </p>
            <ul className="obs-feedback-list">
              {trace.candidates.map((candidate) => {
                const label = candidateLabel(candidate);
                const code = rejectionCode.get(candidate.item_id);
                return (
                  <li key={candidate.item_id}>
                    <div className="obs-feedback-item">
                      <span className="obs-feedback-name">{label}</span>
                      <span className="obs-muted">
                        {candidate.contributions
                          .map((c) => `${LANE_LABELS[c.lane]} #${c.lane_rank}`)
                          .join(", ")}
                        {" · "}
                        {code ? (
                          <span title={code}>Rejected: {humanizeCode(code)}</span>
                        ) : (
                          "Supported"
                        )}
                      </span>
                    </div>
                    <FeedbackControl runId={runId} itemId={candidate.item_id} itemLabel={label} />
                  </li>
                );
              })}
            </ul>
          </section>

          {snapshot && (
            <section
              id="obs-history"
              className="panel-card obs-section"
              aria-labelledby="obs-history-heading"
            >
              <h2 id="obs-history-heading">Run history</h2>
              <PageNavigation
                path={`/observatory/runs/${encodeURIComponent(runId)}`}
                nextCursor={snapshot.runPage.nextCursor}
                previousCursor={snapshot.runPage.previousCursor}
                order={order ?? "asc"}
                label="Run history pages"
              />
              <ul className="obs-run-history">
                {snapshot.runs.map((run) => (
                  <li key={run.run_id}>
                    <Link href={`/observatory/runs/${run.run_id}`} title={run.run_id}>
                      Run {shortId(run.run_id)}
                    </Link>{" "}
                    <span className="obs-muted">
                      · {humanizeCode(run.mode)} · {humanizeCode(run.status)} ·{" "}
                      <time dateTime={run.created_at} title={run.created_at}>
                        {formatUtc(run.created_at)}
                      </time>
                    </span>
                    {run.run_id === runId ? (
                      <> (this run)</>
                    ) : (
                      <>
                        {" "}
                        ·{" "}
                        <Link href={`/observatory/compare?a=${runId}&b=${run.run_id}`}>
                          Compare
                        </Link>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
          <EventReplay trace={trace} />
          <p>
            <Link href={`/observatory/runs/${encodeURIComponent(runId)}/history`}>
              Inspect event history
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}
