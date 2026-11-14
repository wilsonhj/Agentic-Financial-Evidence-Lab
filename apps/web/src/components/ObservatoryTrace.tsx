import Link from "next/link";

import type {
  Candidate,
  QuerySnapshot,
  RetrievalCitation,
  RetrievalTrace,
} from "../lib/observatory/query-source";
import {
  candidateLabel,
  formatUtc,
  humanizeCode,
  shortId,
  splitTimings,
} from "../lib/observatory/labels";
import {
  claimViews,
  decisionTimeline,
  describeRunState,
  laneColumns,
  LANE_LABELS,
  LANES,
  partitionCandidates,
  readerHref,
  type ClaimDisplayStatus,
  type Lane,
} from "../lib/observatory/trace-view";
import { ObservatoryFlowViz } from "./ObservatoryFlowViz";

const CLAIM_OK: ReadonlySet<string> = new Set(["supported"]);
const CLAIM_WARNING: ReadonlySet<string> = new Set(["contradicted", "unverifiable"]);
const CITATION_OK: ReadonlySet<string> = new Set(["entailed"]);
const CITATION_WARNING: ReadonlySet<string> = new Set(["contradictory", "irrelevant"]);
const RUN_OK: ReadonlySet<string> = new Set(["succeeded"]);
const RUN_WARNING: ReadonlySet<string> = new Set(["abstained", "failed"]);

function statusBadgeClass(
  status: string,
  ok: ReadonlySet<string>,
  warning: ReadonlySet<string>,
): string {
  if (ok.has(status)) return "badge badge-ok";
  if (warning.has(status)) return "badge badge-warning";
  return "badge badge-info";
}

function claimBadgeClass(status: ClaimDisplayStatus): string {
  return statusBadgeClass(status, CLAIM_OK, CLAIM_WARNING);
}

function citationBadgeClass(status: RetrievalCitation["status"]): string {
  return statusBadgeClass(status, CITATION_OK, CITATION_WARNING);
}

/** A human label for a code, with the raw code kept in the tooltip. */
function CodeLabel({ code, className }: { code: string; className?: string }) {
  return (
    <span className={className} title={code}>
      {humanizeCode(code)}
    </span>
  );
}

/** Short (8 character) id with the full id in its tooltip. */
export function ShortId({ id }: { id: string }) {
  return (
    <code className="obs-id" title={id}>
      {shortId(id)}
    </code>
  );
}

/**
 * A pin needed to reproduce the run (corpus or index version). Shown in full so
 * it can be read and copied without a hover tooltip, wrapping on narrow screens.
 */
function PinnedId({ id }: { id: string }) {
  return <code className="obs-id obs-id-full">{id}</code>;
}

function UtcTime({ iso }: { iso: string }) {
  return (
    <time dateTime={iso} title={iso}>
      {formatUtc(iso)}
    </time>
  );
}

/** One entry of the run page's in-page section navigation. */
export interface RunSection {
  id: string;
  label: string;
}

/** Sections ObservatoryTrace renders, in display order. */
export const TRACE_SECTIONS: readonly RunSection[] = [
  { id: "obs-plan", label: "Question and plan" },
  { id: "obs-claims", label: "Claims" },
  { id: "obs-flow", label: "Pipeline flow" },
  { id: "obs-lanes", label: "Retrieval lanes" },
  { id: "obs-timeline", label: "Rejections" },
  { id: "obs-budget", label: "Budgets and latency" },
];

/**
 * In-page navigation for the run page. Sticky beside the content on wide
 * screens (so it never overlaps a focused control); a plain wrapped list of
 * links above the content on narrow ones.
 */
export function RunSectionNav({ sections }: { sections: readonly RunSection[] }) {
  return (
    <nav className="obs-section-nav" aria-label="Run sections">
      <p className="obs-section-nav-title" aria-hidden="true">
        On this page
      </p>
      <ul>
        {sections.map((section) => (
          <li key={section.id}>
            <a href={`#${section.id}`}>{section.label}</a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function CandidateRef({
  candidate,
  documentIdByVersionId,
  plan,
  spanId,
}: {
  candidate: Candidate;
  documentIdByVersionId: Readonly<Record<string, string>>;
  plan: RetrievalTrace["plan"];
  /** Span to deep-link; defaults to the candidate's own span. Citations pass their own span. */
  spanId?: string;
}) {
  const href = readerHref(candidate, documentIdByVersionId, spanId, plan);
  const label = candidateLabel(candidate);
  if (!href) {
    return (
      <span className="candidate-ref" title="Reader link unavailable for this version">
        {label}
      </span>
    );
  }
  return (
    <Link className="candidate-ref" href={href}>
      Open evidence <span className="visually-hidden">for {label} in the reader</span>
    </Link>
  );
}

function PlanSection({ snapshot, trace }: { snapshot?: QuerySnapshot; trace: RetrievalTrace }) {
  const { plan } = trace;
  const filters = [
    plan.filters.forms?.length ? `Forms: ${plan.filters.forms.join(", ")}` : null,
    plan.filters.periods?.length ? `Periods: ${plan.filters.periods.join(", ")}` : null,
  ].filter(Boolean);
  return (
    <section id="obs-plan" className="panel-card obs-section" aria-labelledby="obs-plan-heading">
      <h2 id="obs-plan-heading">Query plan</h2>
      {snapshot && <p className="obs-question">{snapshot.question}</p>}
      <p className="obs-status">
        Run status:{" "}
        <span className={statusBadgeClass(trace.status, RUN_OK, RUN_WARNING)} title={trace.status}>
          {humanizeCode(trace.status)}
        </span>
        <span className="obs-muted">
          {" "}
          · Run <ShortId id={trace.run_id} />
          {trace.started_at && (
            <>
              {" "}
              · started <UtcTime iso={trace.started_at} />
            </>
          )}
        </span>
      </p>
      <dl className="obs-meta">
        <div>
          <dt>Intent</dt>
          <dd>
            <CodeLabel code={plan.intent} />
          </dd>
        </div>
        <div>
          <dt>Effective cutoff</dt>
          <dd>
            <UtcTime iso={plan.effective_as_of} />
          </dd>
        </div>
        <div>
          <dt>Corpus version</dt>
          <dd>
            <PinnedId id={plan.corpus_version_id} />
          </dd>
        </div>
        <div>
          <dt>Index version</dt>
          <dd>
            <PinnedId id={plan.index_version_id} />
          </dd>
        </div>
        <div>
          <dt>Lanes</dt>
          <dd>
            {plan.lanes.map((lane) => LANE_LABELS[lane as Lane] ?? humanizeCode(lane)).join(", ")}
          </dd>
        </div>
        <div>
          <dt>Filters</dt>
          <dd>{filters.join(" · ") || "None"}</dd>
        </div>
      </dl>
      {plan.variants.length > 0 && (
        <>
          <h3>Query variants</h3>
          <ul className="obs-variants">
            {plan.variants.map((variant, index) => (
              <li key={index}>{variant}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function BudgetSection({ trace }: { trace: RetrievalTrace }) {
  const { budgets } = trace.plan;
  const usage = trace.budget_usage;
  const { stages: timings, totalMs } = splitTimings(trace.timings_ms);
  return (
    <section
      id="obs-budget"
      className="panel-card obs-section"
      aria-labelledby="obs-budget-heading"
    >
      <h2 id="obs-budget-heading">Budgets, latency and cost</h2>
      <div className="obs-budget-grid">
        <table className="doc-table obs-num-table">
          <caption>Budget and cost</caption>
          <thead>
            <tr>
              <th scope="col">Metric</th>
              <th scope="col" className="obs-num">
                Value
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Context items (used / limit)</th>
              <td className="obs-num">
                {usage.context_items} / {budgets.context_items}
              </td>
            </tr>
            <tr>
              <th scope="row">Context tokens</th>
              <td className="obs-num">{usage.context_tokens}</td>
            </tr>
            <tr>
              <th scope="row">Input tokens</th>
              <td className="obs-num">{usage.input_tokens}</td>
            </tr>
            <tr>
              <th scope="row">Output tokens</th>
              <td className="obs-num">{usage.output_tokens}</td>
            </tr>
            <tr>
              <th scope="row">Cost (USD)</th>
              <td className="obs-num">{trace.cost_usd}</td>
            </tr>
          </tbody>
        </table>
        {timings.length === 0 && totalMs > 0 && (
          <p className="obs-muted">
            <strong>Total latency:</strong> {totalMs} ms. No per-stage timings were recorded.
          </p>
        )}
        {timings.length > 0 && (
          <table className="doc-table obs-num-table">
            <caption>Stage latency</caption>
            <thead>
              <tr>
                <th scope="col">Stage</th>
                <th scope="col" className="obs-num">
                  Latency (ms)
                </th>
                <th scope="col">Share of total</th>
              </tr>
            </thead>
            <tbody>
              {timings.map(([stage, ms]) => {
                const pct = totalMs > 0 ? Math.min(100, Math.round((ms / totalMs) * 100)) : 0;
                return (
                  <tr key={stage}>
                    <th scope="row">
                      <CodeLabel code={stage} />
                    </th>
                    <td className="obs-num">{ms}</td>
                    <td>
                      <span className="obs-share">
                        <span className="obs-share-track" aria-hidden="true">
                          <span className="obs-share-fill" style={{ width: `${pct}%` }} />
                        </span>
                        <span className="obs-num">{pct}%</span>
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr>
                <th scope="row">Total</th>
                <td className="obs-num">{totalMs}</td>
                <td />
              </tr>
            </tfoot>
          </table>
        )}
      </div>
    </section>
  );
}

function LaneSection({
  trace,
  documentIdByVersionId,
}: {
  trace: RetrievalTrace;
  documentIdByVersionId: Readonly<Record<string, string>>;
}) {
  const columns = laneColumns(trace);
  const { rejected } = partitionCandidates(trace);
  const rejectionCode = new Map(rejected.map(({ candidate, code }) => [candidate.item_id, code]));
  return (
    <section id="obs-lanes" className="panel-card obs-section" aria-labelledby="obs-lanes-heading">
      <h2 id="obs-lanes-heading">Retrieval lanes</h2>
      <div className="obs-lane-grid">
        {LANES.map((lane) => (
          <div key={lane} className="obs-lane">
            <h3 id={`obs-lane-${lane}-heading`}>{LANE_LABELS[lane]}</h3>
            {columns[lane].length === 0 ? (
              <p className="obs-empty">No candidates in this lane.</p>
            ) : (
              <div
                className="obs-table-scroll"
                role="region"
                aria-labelledby={`obs-lane-${lane}-heading`}
                tabIndex={0}
              >
                <table className="doc-table obs-lane-table">
                  <caption className="visually-hidden">{LANE_LABELS[lane]} lane candidates</caption>
                  <thead>
                    <tr>
                      <th scope="col" className="obs-num">
                        Lane rank
                      </th>
                      <th scope="col" className="obs-num">
                        Raw
                      </th>
                      <th scope="col" className="obs-num">
                        Norm
                      </th>
                      <th scope="col" className="obs-num">
                        RRF
                      </th>
                      <th scope="col" className="obs-num">
                        Fused (rank / score)
                      </th>
                      <th scope="col" className="obs-num">
                        Rerank (rank / score)
                      </th>
                      <th scope="col">Status</th>
                      <th scope="col">Evidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {columns[lane].map((row) => {
                      const code = rejectionCode.get(row.candidate.item_id);
                      return (
                        <tr key={`${row.candidate.item_id}-${row.contribution.variant_index}`}>
                          <td className="obs-num">{row.contribution.lane_rank}</td>
                          <td className="obs-num">{row.contribution.raw_score}</td>
                          <td className="obs-num">{row.contribution.normalized_score ?? "—"}</td>
                          <td className="obs-num">{row.contribution.rrf_contribution}</td>
                          <td className="obs-num">
                            {row.fusedRank ?? "—"} / {row.fusedScore}
                          </td>
                          <td className="obs-num">
                            {row.rerankRank ?? "—"} / {row.rerankScore ?? "—"}
                          </td>
                          <td>
                            <span
                              className={row.supported ? "badge badge-ok" : "badge badge-warning"}
                              title={
                                row.supported ? "supported" : `rejected: ${code ?? "rejected"}`
                              }
                            >
                              {row.supported ? "Supported" : "Rejected"}
                            </span>
                          </td>
                          <td>
                            <CandidateRef
                              candidate={row.candidate}
                              documentIdByVersionId={documentIdByVersionId}
                              plan={trace.plan}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function TimelineSection({ trace }: { trace: RetrievalTrace }) {
  const entries = decisionTimeline(trace);
  const { rejected } = partitionCandidates(trace);
  const byItemId = new Map(trace.candidates.map((candidate) => [candidate.item_id, candidate]));
  const describeItem = (itemId: string) => {
    const candidate = byItemId.get(itemId);
    return candidate ? candidateLabel(candidate) : `Item ${shortId(itemId)}`;
  };
  return (
    <section
      id="obs-timeline"
      className="panel-card obs-section"
      aria-labelledby="obs-timeline-heading"
    >
      <h2 id="obs-timeline-heading">Filter and rejection timeline</h2>
      {entries.length === 0 ? (
        <p className="obs-empty">No decisions recorded.</p>
      ) : (
        <ol className="obs-timeline">
          {entries.map((entry, index) => (
            <li key={index}>
              <span className="badge badge-info" title={entry.stage}>
                {humanizeCode(entry.stage)}
              </span>{" "}
              <strong>{humanizeCode(entry.code)}</strong>{" "}
              <code className="obs-code">{entry.code}</code>
              <span className="obs-muted obs-timeline-detail">
                {entry.itemIds.length === 0
                  ? "No items"
                  : entry.itemIds.map(describeItem).join("; ")}{" "}
                · <UtcTime iso={entry.occurredAt} />
              </span>
            </li>
          ))}
        </ol>
      )}
      <h3>Rejected candidates</h3>
      {rejected.length === 0 ? (
        <p className="obs-empty">No rejected candidates.</p>
      ) : (
        <ul className="obs-rejected">
          {rejected.map(({ candidate, code }) => {
            const duplicateOf = candidate.decision_detail?.duplicate_of;
            return (
              <li key={candidate.item_id}>
                <strong>{humanizeCode(code)}</strong> <code className="obs-code">{code}</code> —{" "}
                {candidateLabel(candidate)}{" "}
                <span className="obs-muted">
                  · published <UtcTime iso={candidate.published_at} />
                  {typeof duplicateOf === "string" && (
                    <> · duplicate of {describeItem(duplicateOf)}</>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function ClaimsSection({
  trace,
  documentIdByVersionId,
}: {
  trace: RetrievalTrace;
  documentIdByVersionId: Readonly<Record<string, string>>;
}) {
  const views = claimViews(trace);
  const byItemId = new Map(trace.candidates.map((candidate) => [candidate.item_id, candidate]));
  const counts = new Map<string, number>();
  for (const view of views)
    counts.set(view.displayStatus, (counts.get(view.displayStatus) ?? 0) + 1);
  return (
    <section
      id="obs-claims"
      className="panel-card obs-section"
      aria-labelledby="obs-claims-heading"
    >
      <h2 id="obs-claims-heading">Claims and citations</h2>
      {views.length === 0 ? (
        <p className="obs-empty">No claims generated.</p>
      ) : (
        <>
          <p className="obs-muted obs-claims-summary">
            {views.length} claim{views.length === 1 ? "" : "s"}:{" "}
            {[...counts]
              .map(([status, count]) => `${count} ${humanizeCode(status).toLowerCase()}`)
              .join(", ")}
          </p>
          <ul className="obs-claims">
            {views.map(({ claim, displayStatus, downgraded }) => (
              <li key={claim.id} className="obs-claim">
                <p className="obs-claim-text">
                  <span className={claimBadgeClass(displayStatus)} title={displayStatus}>
                    {humanizeCode(displayStatus)}
                  </span>{" "}
                  {claim.text}
                </p>
                {downgraded && (
                  <p className="obs-muted" role="note">
                    Downgraded: cites evidence outside the supported set.
                  </p>
                )}
                <ul className="obs-citations">
                  {claim.citations.map((citation, index) => {
                    const candidate = byItemId.get(citation.item_id);
                    return (
                      <li key={index}>
                        <span
                          className={citationBadgeClass(citation.status)}
                          title={citation.status}
                        >
                          {humanizeCode(citation.status)}
                        </span>{" "}
                        {candidate ? (
                          <>
                            <span className="obs-muted">{candidateLabel(candidate)}</span>{" "}
                            <CandidateRef
                              candidate={candidate}
                              documentIdByVersionId={documentIdByVersionId}
                              plan={trace.plan}
                              spanId={citation.source_span_id}
                            />
                          </>
                        ) : (
                          <span className="obs-muted">
                            Item <ShortId id={citation.item_id} />
                          </span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

/**
 * Presentational Observatory trace view. Pure and server-renderable: every
 * "supported" affordance is gated by the trace-view integrity guard, so
 * future, cross-version or rejected evidence can never render as supported.
 * Sections are ordered for a reader: the question and run status, then the
 * claims and their verdicts, then how the pipeline got there.
 */
export function ObservatoryTrace({
  trace,
  snapshot,
  documentIdByVersionId,
}: {
  trace: RetrievalTrace;
  snapshot?: QuerySnapshot;
  documentIdByVersionId: Readonly<Record<string, string>>;
}) {
  const runState = describeRunState(trace.status);
  return (
    <div className="obs-trace">
      <PlanSection snapshot={snapshot} trace={trace} />
      {runState && (
        <section
          className={`reader-banner obs-runstate ${runState.tone === "warning" ? "citation-error" : ""}`}
          role={runState.tone === "warning" ? "alert" : "status"}
          aria-labelledby="obs-runstate-heading"
        >
          <h2 id="obs-runstate-heading">{runState.heading}</h2>
          <p>{runState.description}</p>
        </section>
      )}
      <ClaimsSection trace={trace} documentIdByVersionId={documentIdByVersionId} />
      <ObservatoryFlowViz trace={trace} />
      <LaneSection trace={trace} documentIdByVersionId={documentIdByVersionId} />
      <TimelineSection trace={trace} />
      <BudgetSection trace={trace} />
    </div>
  );
}
