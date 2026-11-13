"use client";

import { useState } from "react";
import type { RetrievalTrace } from "../lib/observatory/query-source";
import {
  claimViews,
  LANE_LABELS,
  LANES,
  laneColumns,
  partitionCandidates,
  type Lane,
  type RejectedCandidate,
} from "../lib/observatory/trace-view";

const SHORT_REJECTION_LABELS: Record<string, string> = {
  temporal_after_cutoff: "cutoff",
  cross_version: "version",
  dedupe_near_duplicate: "dedupe",
};

/**
 * The reason codes behind the rejected candidates, in first-seen order: a short
 * form that fits the box, and the exact codes for its tooltip.
 */
export function rejectionSummary(rejected: RejectedCandidate[]): { short: string; full: string } {
  const codes = [...new Set(rejected.map((item) => item.code))];
  if (codes.length === 0) return { short: "none", full: "No candidates rejected" };
  const labels = codes.map((code) => SHORT_REJECTION_LABELS[code] ?? code);
  const short =
    labels.length > 3
      ? `${labels.slice(0, 2).join(", ")} +${labels.length - 2} more`
      : labels.join(", ");
  return { short, full: codes.join(", ") };
}

/**
 * Lane colours come from theme tokens (see `.obs-flow-lane-*` in
 * styles/observatory.css) so the diagram follows light and dark themes. The
 * lane name is always printed too, so colour is never the only cue.
 */
function laneClass(lane: Lane): string {
  return `obs-flow-lane obs-flow-lane-${lane}`;
}

/**
 * Interactive 4-Lane RRF Fusion Sankey Flow & Latency/Budget Gauge for the
 * Search Observatory. Uses `laneColumns`, `partitionCandidates` and
 * `claimViews` so future-dated or cross-version evidence is never counted as
 * supported.
 */
export function ObservatoryFlowViz({ trace }: { trace: RetrievalTrace }) {
  const [selectedLane, setSelectedLane] = useState<Lane | null>(null);
  const columns = laneColumns(trace);
  const { supported, rejected } = partitionCandidates(trace);
  const rejectedReasons = rejectionSummary(rejected);
  const claims = claimViews(trace);

  const supportedClaims = claims.filter((c) => c.displayStatus === "supported").length;
  const flaggedClaims = claims.length - supportedClaims;

  const totalCandidates = supported.length + rejected.length;
  const timingEntries = Object.entries(trace.timings_ms);
  const totalLatencyMs = timingEntries.reduce((acc, [, ms]) => acc + ms, 0);

  const contextItemsUsed = trace.budget_usage.context_items;
  const contextItemsCap = Math.max(1, trace.plan.budgets.context_items);
  const contextUtilizationPct = Math.min(
    100,
    Math.round((contextItemsUsed / contextItemsCap) * 100),
  );

  const selectedLaneRows = selectedLane ? columns[selectedLane] : null;
  const selectedLaneSupportedCount = selectedLaneRows
    ? selectedLaneRows.filter((row) => row.supported).length
    : null;

  return (
    <section
      id="obs-flow"
      className="panel-card obs-flow-card obs-section"
      data-testid="observatory-flow-viz"
      aria-labelledby="obs-flow-heading"
    >
      <div className="obs-flow-header">
        <div>
          <h2 id="obs-flow-heading">Pipeline flow &amp; RRF fusion arena</h2>
          <p className="obs-muted obs-flow-subtitle">
            4-lane candidate retrieval → Reciprocal Rank Fusion (<code>k=60</code>) → Temporal &amp;
            version gates → Claim entailment
          </p>
        </div>
        <div className="obs-flow-pills">
          {selectedLane && selectedLaneRows ? (
            <span className="badge badge-info" data-testid="obs-flow-selected-lane-summary">
              {LANE_LABELS[selectedLane]}: {selectedLaneRows.length} hit
              {selectedLaneRows.length === 1 ? "" : "s"} ({selectedLaneSupportedCount} supported)
            </span>
          ) : null}
          <span className="badge badge-ok">{supported.length} supported</span>
          <span className="badge badge-warning">{rejected.length} rejected</span>
          <span className="badge badge-info">{totalLatencyMs} ms total</span>
        </div>
      </div>

      <div className="viz3d-controls" role="group" aria-label="Filter flow by retrieval lane">
        <button
          type="button"
          data-testid="button-obs-flow-lane-all"
          aria-pressed={selectedLane === null}
          onClick={() => setSelectedLane(null)}
        >
          All lanes
        </button>
        {LANES.map((lane) => (
          <button
            key={lane}
            type="button"
            data-testid={`button-obs-flow-lane-${lane}`}
            aria-pressed={selectedLane === lane}
            onClick={() => setSelectedLane((prev) => (prev === lane ? null : lane))}
          >
            {LANE_LABELS[lane]} ({columns[lane].length})
          </button>
        ))}
      </div>

      {/* Below ~600px the diagram scrolls inside its own region instead of
          shrinking to unreadable text. */}
      <div
        className="obs-flow-scroll"
        role="region"
        aria-label="Pipeline flow diagram"
        tabIndex={0}
      >
        <svg
          viewBox="0 0 860 250"
          className="obs-flow-svg"
          role="img"
          aria-label={`Retrieval pipeline flow: ${totalCandidates} candidates across 4 lanes fused via RRF k=60 into ${supported.length} supported items, ${rejected.length} rejected items, and ${claims.length} claims`}
        >
          {/* Stage Column Headers */}
          <text x="24" y="22" fill="currentColor" fontSize="11" fontWeight="700" opacity="0.75">
            1. RETRIEVAL LANES
          </text>
          <text x="295" y="22" fill="currentColor" fontSize="11" fontWeight="700" opacity="0.75">
            2. RRF FUSION (k=60)
          </text>
          <text x="530" y="22" fill="currentColor" fontSize="11" fontWeight="700" opacity="0.75">
            3. CUTOFF &amp; VERSION GATES
          </text>
          <text x="720" y="22" fill="currentColor" fontSize="11" fontWeight="700" opacity="0.75">
            4. CLAIMS
          </text>

          {/* Left: 4 Retrieval Lanes */}
          {LANES.map((lane, index) => {
            const rows = columns[lane];
            const y = 38 + index * 50;
            const isHighlighted = selectedLane === null || selectedLane === lane;
            const strokeWidth = Math.max(2, Math.min(12, rows.length * 4));
            return (
              <g
                key={lane}
                data-testid={`obs-flow-lane-${lane}`}
                className={laneClass(lane)}
                opacity={isHighlighted ? 1 : 0.3}
              >
                {/* Curved Sankey ribbon to RRF Nexus */}
                <path
                  d={`M 184 ${y + 18} C 235 ${y + 18}, 240 128, 290 128`}
                  className="obs-flow-ribbon"
                  fill="none"
                  strokeWidth={strokeWidth}
                  strokeOpacity={rows.length > 0 ? 0.65 : 0.2}
                  strokeDasharray={rows.length > 0 ? undefined : "4 4"}
                />
                <rect
                  x="20"
                  y={y}
                  width="164"
                  height="36"
                  rx="7"
                  className="obs-flow-lane-box"
                  fillOpacity={selectedLane === lane ? "0.28" : "0.14"}
                  strokeWidth={selectedLane === lane ? "2.4" : "1.5"}
                />
                <text x="32" y={y + 16} fill="currentColor" fontSize="12" fontWeight="700">
                  {LANE_LABELS[lane]}
                </text>
                <text x="32" y={y + 29} fill="currentColor" fontSize="10" opacity="0.8">
                  {rows.length} hit{rows.length === 1 ? "" : "s"}
                </text>
              </g>
            );
          })}

          {/* Center-Left: RRF k=60 Fusion Nexus */}
          <g data-testid="obs-flow-rrf-nexus">
            <rect
              x="290"
              y="84"
              width="156"
              height="88"
              rx="10"
              className="obs-flow-box obs-flow-box-info"
              strokeWidth="2"
            />
            <text
              x="368"
              y="114"
              textAnchor="middle"
              fill="currentColor"
              fontSize="13"
              fontWeight="700"
            >
              RRF Fusion
            </text>
            <text
              x="368"
              y="133"
              textAnchor="middle"
              className="obs-flow-text-accent"
              fontSize="11"
            >
              k = 60 · {totalCandidates} candidates
            </text>
            <text x="368" y="152" textAnchor="middle" className="obs-flow-text-muted" fontSize="10">
              Deterministic tie-break
            </text>
          </g>

          {/* Flow from RRF Nexus to Supported vs Rejected Gates */}
          <path
            d="M 446 114 C 485 114, 490 78, 530 78"
            fill="none"
            className="obs-flow-path-ok"
            strokeWidth={Math.max(3, supported.length * 4)}
            strokeOpacity="0.75"
          />
          <path
            d="M 446 144 C 485 144, 490 178, 530 178"
            fill="none"
            className="obs-flow-path-warning"
            strokeWidth={Math.max(2, rejected.length * 4)}
            strokeOpacity="0.75"
          />

          {/* Center-Right Top: Supported Context Set */}
          <g data-testid="obs-flow-supported-box">
            <rect
              x="530"
              y="48"
              width="148"
              height="62"
              rx="8"
              className="obs-flow-box obs-flow-box-ok"
              strokeWidth="1.5"
            />
            <text x="544" y="72" className="obs-flow-text-ok" fontSize="12" fontWeight="700">
              Supported Set ({supported.length})
            </text>
            <text x="544" y="90" className="obs-flow-text-muted" fontSize="10">
              At or before the cutoff
            </text>
          </g>

          {/* Center-Right Bottom: Gate-Rejected Candidates */}
          <g data-testid="obs-flow-rejected-box">
            <title>{`Rejection codes: ${rejectedReasons.full}`}</title>
            <rect
              x="530"
              y="146"
              width="148"
              height="62"
              rx="8"
              className="obs-flow-box obs-flow-box-warning"
              strokeWidth="1.5"
            />
            <text x="544" y="170" className="obs-flow-text-warning" fontSize="12" fontWeight="700">
              Gate Rejected ({rejected.length})
            </text>
            <text
              x="544"
              y="188"
              className="obs-flow-text-muted"
              fontSize="10"
              data-testid="obs-flow-rejected-reasons"
            >
              {rejectedReasons.short}
            </text>
          </g>

          {/* Flow from Supported to Claims */}
          <path
            d="M 678 78 C 698 78, 700 112, 720 112"
            fill="none"
            className="obs-flow-path-ok"
            strokeWidth={Math.max(3, claims.length * 3.5)}
            strokeOpacity="0.8"
          />

          {/* Right: Claim Decomposition Box */}
          <g data-testid="obs-flow-claims-box">
            <rect
              x="720"
              y="68"
              width="124"
              height="92"
              rx="8"
              className="obs-flow-box obs-flow-box-claims"
              strokeWidth="1.5"
            />
            <text x="732" y="92" fill="currentColor" fontSize="12" fontWeight="700">
              Claims ({claims.length})
            </text>
            <text x="732" y="114" className="obs-flow-text-ok" fontSize="10.5">
              • {supportedClaims} supported
            </text>
            <text x="732" y="132" className="obs-flow-text-warning" fontSize="10.5">
              • {flaggedClaims} flagged
            </text>
            <text x="732" y="148" className="obs-flow-text-muted" fontSize="9.5">
              Span-hash checked
            </text>
          </g>
        </svg>
      </div>

      {/* Visual Context Budget & Stage Latency Bar */}
      <div className="obs-flow-meters">
        <div className="obs-meter-box">
          <div className="obs-meter-label">
            <span>
              <strong>Context budget utilization:</strong> {contextItemsUsed} / {contextItemsCap}{" "}
              items ({trace.budget_usage.context_tokens} tokens)
            </span>
            <span>{contextUtilizationPct}%</span>
          </div>
          <div className="obs-meter-track" aria-hidden="true">
            <div className="obs-meter-fill" style={{ width: `${contextUtilizationPct}%` }} />
          </div>
        </div>

        {/* Per-stage latency lives in one place: the "Budgets, latency and cost" section. */}
        {timingEntries.length > 0 && (
          <p className="obs-meter-box obs-muted">
            <span>
              <strong>Total latency:</strong> {totalLatencyMs} ms.{" "}
              <a href="#obs-budget">Per-stage latency and cost</a>
            </span>
          </p>
        )}
      </div>
    </section>
  );
}
