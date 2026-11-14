"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import {
  guards,
  type Proposal,
  type Permissions,
  type Conflict,
  type Review,
  type Schemas,
} from "../../lib/extraction/contracts";
import {
  buildReview,
  prepareRequest,
  sendPrepared,
  statusMessage,
  type PendingRequest,
} from "../../lib/extraction/review-state";
import { PayloadFields } from "./display";
import { RunLink, StatusBadge, humanize } from "./labels";

type SortKey = "metric" | "kind" | "run" | "state" | "confidence" | "blockers";
type SortState = { key: SortKey; direction: "ascending" | "descending" } | null;

const blockerCount = (p: Proposal) => p.validations.filter((v) => v.status !== "pass").length;

/** Display-only ordering of the rows already loaded on this page. */
function sortProposals(rows: Proposal[], sort: SortState): Proposal[] {
  if (!sort) return rows;
  const value = (p: Proposal): string | number | null => {
    switch (sort.key) {
      case "metric":
        return p.metric_id;
      case "kind":
        return humanize(p.kind);
      case "run":
        return p.run_id;
      case "state":
        return humanize(p.state);
      case "confidence": {
        const n = p.record_confidence === null ? NaN : Number(p.record_confidence);
        return Number.isFinite(n) ? n : null;
      }
      case "blockers":
        return blockerCount(p);
    }
  };
  const factor = sort.direction === "ascending" ? 1 : -1;
  return rows
    .map((p, index) => ({ p, index, v: value(p) }))
    .sort((a, b) => {
      // Uncalibrated (null) confidence always sorts last; it is never treated as zero.
      if (a.v === null || b.v === null)
        return a.v === b.v ? a.index - b.index : a.v === null ? 1 : -1;
      const order =
        typeof a.v === "number" && typeof b.v === "number"
          ? a.v - b.v
          : String(a.v).localeCompare(String(b.v));
      return order * factor || a.index - b.index;
    })
    .map(({ p }) => p);
}

function isReviewableState(state: Proposal["state"]): boolean {
  switch (state) {
    case "proposed":
    case "needs_review":
      return true;
    case "accepted":
    case "rejected":
    case "superseded":
      return false;
    default: {
      const _never: never = state;
      return _never;
    }
  }
}

function keepReviewableIds(
  ids: string[],
  rows: Proposal[],
  states: Record<string, string> = {},
): string[] {
  return ids.filter((id) => {
    const state = states[id] ?? rows.find((row) => row.id === id)?.state;
    return state === "proposed" || state === "needs_review" ? isReviewableState(state) : false;
  });
}

export function ReviewQueue({
  proposals,
  permissions: initialPermissions,
}: {
  proposals: Proposal[];
  permissions: Permissions;
}) {
  const [rows, setRows] = useState(proposals);
  const [permissions, setPermissions] = useState(initialPermissions);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [action, setAction] = useState<Review["action"]>("accept");
  const [reason, setReason] = useState("");
  const [patch, setPatch] = useState("");
  const [groups, setGroups] = useState<Conflict[]>([]);
  const [winners, setWinners] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const [compared, setCompared] = useState(false);
  const [result, setResult] = useState<Schemas["ReviewResult"] | null>(null);
  const [sort, setSort] = useState<SortState>(null);
  const pending = useRef<PendingRequest | undefined>(undefined);
  const selected = rows.filter((p) => selectedIds.includes(p.id));
  const editable = selected.every((p) => ["proposed", "needs_review"].includes(p.state));
  const permitted = permissions.allowed_actions.includes(action);
  const change = () => {
    pending.current = undefined;
    setResult(null);
  };
  async function json(path: string) {
    const response = await fetch(`/api/extraction/${path}`, { cache: "no-store" });
    if (!response.ok) throw new Error(statusMessage(response.status));
    return response.json() as Promise<unknown>;
  }
  async function refresh(contextOnly = false) {
    setBusy(true);
    setMessage("");
    try {
      const capability = await json("permissions");
      if (!guards.permissions(capability)) throw new Error("Invalid permissions response");
      setPermissions(capability);
      const current = contextOnly
        ? selected
        : await Promise.all(
            selected.map(async (p) => {
              const value = await json(`proposals/${p.id}`);
              if (!guards.proposal(value) || value.id !== p.id)
                throw new Error("Invalid proposal response");
              return value;
            }),
          );
      const ids = [...new Set(current.flatMap((p) => p.conflict_ids))];
      if (ids.length > 100) throw new Error("Too many conflict groups for one atomic review");
      const conflicts = await Promise.all(
        ids.map(async (id) => {
          const value = await json(`conflicts/${id}`);
          if (!guards.conflict(value) || value.id !== id)
            throw new Error("Invalid conflict response");
          return value;
        }),
      );
      setGroups(conflicts);
      if (!contextOnly) {
        const nextRows = rows.map((p) => current.find((c) => c.id === p.id) ?? p);
        const remaining = keepReviewableIds(selectedIds, nextRows);
        setRows(nextRows);
        setSelectedIds(remaining);
        setCompared(remaining.length > 0);
        setWinners((ids) => ids.filter((id) => remaining.includes(id)));
        if (!remaining.length) {
          setGroups([]);
          setStale(false);
        }
        pending.current = undefined;
        setMessage(
          remaining.length
            ? "Current versions loaded below. Compare them with your preserved draft, then use the refreshed versions explicitly."
            : "Selected proposals are no longer reviewable. Choose another pending proposal.",
        );
      } else {
        setMessage("Complete conflict membership loaded. Choose the winners explicitly.");
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Unable to refresh comparison");
    } finally {
      setBusy(false);
    }
  }
  async function submit() {
    setBusy(true);
    setMessage("");
    try {
      const body = buildReview(selected, action, reason, patch, groups, winners);
      pending.current = prepareRequest("review", "POST", body, null, pending.current);
      const response = await sendPrepared(pending.current);
      if (!response.ok) {
        setMessage(statusMessage(response.status));
        if (response.status === 412) {
          setStale(true);
          setCompared(false);
        }
        return;
      }
      const value: unknown = await response.json();
      if (
        !guards.result(value) ||
        value.action !== action ||
        ![value.proposal_states, value.proposal_versions].every(
          (map) =>
            Object.keys(map).length === selected.length &&
            selected.every((p) => Object.hasOwn(map, p.id)),
        )
      )
        throw new Error("Invalid review receipt; refresh before proceeding");
      setResult(value);
      const nextRows = rows.map((p) =>
        value.proposal_states[p.id]
          ? { ...p, state: value.proposal_states[p.id]!, version: value.proposal_versions[p.id]! }
          : p,
      );
      const remaining = keepReviewableIds(selectedIds, nextRows, value.proposal_states);
      setRows(nextRows);
      setSelectedIds(remaining);
      setCompared(false);
      setWinners((ids) => ids.filter((id) => remaining.includes(id)));
      if (!remaining.length) {
        setGroups([]);
      }
      setMessage(
        `Atomic ${action} completed for ${selected.length} selected proposals. Unselected proposals were not submitted.`,
      );
      pending.current = undefined;
    } catch (e) {
      setMessage(
        e instanceof Error
          ? e.message
          : "Network interrupted. Retry retains the same request and key.",
      );
    } finally {
      setBusy(false);
    }
  }
  const sortedRows = sortProposals(rows, sort);
  const sortHeader = (key: SortKey, label: string, numeric = false) => {
    const active = sort?.key === key;
    const direction = active ? sort.direction : undefined;
    return (
      <th scope="col" aria-sort={direction} className={numeric ? "extraction-num" : undefined}>
        <button
          type="button"
          className="extraction-sort"
          onClick={() =>
            setSort({ key, direction: direction === "ascending" ? "descending" : "ascending" })
          }
        >
          {label}
          <span aria-hidden="true" className="extraction-sort-indicator">
            {direction === "ascending" ? "▲" : direction === "descending" ? "▼" : "⇅"}
          </span>
        </button>
      </th>
    );
  };
  return (
    <section aria-label="Review proposals" className="review-queue">
      {!rows.length ? (
        <p className="extraction-empty">No proposals on this page.</p>
      ) : (
        <div
          className="extraction-table-scroll"
          role="region"
          aria-label="Proposals on this page, scrollable"
          tabIndex={0}
        >
          <table className="extraction-table">
            <caption>
              Proposals on this page
              <span className="extraction-caption-hint"> · Sorting applies to this page only</span>
            </caption>
            <thead>
              <tr>
                <th scope="col" className="extraction-select-col">
                  Select
                </th>
                {sortHeader("metric", "Metric")}
                {sortHeader("kind", "Kind")}
                {sortHeader("run", "Source run")}
                {sortHeader("state", "State")}
                {sortHeader("confidence", "Confidence", true)}
                {sortHeader("blockers", "Blockers")}
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((p) => {
                const blockers = p.validations.filter((v) => v.status !== "pass");
                const isSelected = selectedIds.includes(p.id);
                return (
                  <tr key={p.id} className={isSelected ? "is-selected" : undefined}>
                    <td className="extraction-select-col">
                      <input
                        type="checkbox"
                        aria-label={`Select ${p.metric_id} ${p.id}`}
                        checked={isSelected}
                        disabled={busy || !["proposed", "needs_review"].includes(p.state)}
                        onChange={(e) => {
                          change();
                          setGroups([]);
                          setWinners([]);
                          setSelectedIds(
                            e.target.checked
                              ? [...selectedIds, p.id]
                              : selectedIds.filter((id) => id !== p.id),
                          );
                        }}
                      />
                    </td>
                    <td>
                      <Link href={`/extractions/${p.id}`} className="extraction-strong-link">
                        {p.metric_id}
                      </Link>
                    </td>
                    <td>{humanize(p.kind)}</td>
                    <td className="extraction-nowrap">
                      <RunLink id={p.run_id} />
                    </td>
                    <td className="extraction-nowrap">
                      <StatusBadge status={p.state} />{" "}
                      <span className="extraction-version">v{p.version}</span>
                    </td>
                    <td className="extraction-num">
                      {p.record_confidence ?? (
                        <span className="extraction-muted">Uncalibrated</span>
                      )}
                    </td>
                    <td>
                      {blockers.length ? (
                        <ul className="extraction-badge-list">
                          {blockers.map((v, index) => (
                            <li key={`${v.code}-${index}`}>
                              <StatusBadge status={v.status} label={`${v.status}: ${v.code}`} />
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <span className="extraction-muted">No recorded blockers</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <section
        className={selected.length ? "review-selection-bar has-selection" : "review-selection-bar"}
        aria-label="Selected proposals"
      >
        <div className="review-selection-head">
          <p className="review-selection-count">
            <strong>{selected.length} selected.</strong> Review is atomic: the whole selected batch
            succeeds or none of it does.
          </p>
          <div className="review-selection-tools">
            <button
              type="button"
              className="extraction-button"
              onClick={() => void refresh(true)}
              disabled={busy || !selected.length}
            >
              Load complete conflict context
            </button>
            <button
              type="button"
              className="extraction-button"
              disabled={busy}
              onClick={() => void refresh()}
            >
              Refresh comparison and permissions
            </button>
          </div>
        </div>
        {groups.map((group) => (
          <fieldset key={group.id} className="review-conflict">
            <legend>
              Conflict <span className="extraction-mono">{group.id}</span>{" "}
              <StatusBadge status={group.status} />
            </legend>
            <p>{group.reason_codes.join(", ")}</p>
            <p className="extraction-muted extraction-mono">ETag {group.etag}</p>
            <ul className="review-conflict-members">
              {Object.entries(group.member_versions).map(([id, version]) => (
                <li key={id}>
                  <span>
                    <Link href={`/extractions/${id}`} className="extraction-mono">
                      {id}
                    </Link>{" "}
                    version {version}
                  </span>
                  {selectedIds.includes(id) && (
                    <label className="extraction-check">
                      <input
                        type="checkbox"
                        checked={winners.includes(id)}
                        disabled={busy}
                        onChange={(e) => {
                          change();
                          setWinners(
                            e.target.checked ? [...winners, id] : winners.filter((w) => w !== id),
                          );
                        }}
                      />
                      Explicit winner
                    </label>
                  )}
                </li>
              ))}
            </ul>
            {group.resolution && <p>Recorded decision: {group.resolution.reason}</p>}
          </fieldset>
        ))}
        <form
          className="review-form"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <div className="extraction-field review-form-action">
            <label htmlFor="review-action">Review action</label>
            <select
              id="review-action"
              className="extraction-control"
              value={action}
              disabled={busy}
              onChange={(e) => {
                const value = e.target.value;
                if (["accept", "edit", "reject", "merge"].includes(value)) {
                  change();
                  setAction(value as Review["action"]);
                }
              }}
            >
              {(["accept", "edit", "reject", "merge"] as const).map((a) => (
                <option key={a} value={a} disabled={!permissions.allowed_actions.includes(a)}>
                  {humanize(a)}
                </option>
              ))}
            </select>
          </div>
          <div className="extraction-field review-form-reason">
            <label htmlFor="review-reason">Reason</label>
            <textarea
              id="review-reason"
              className="extraction-control"
              rows={2}
              value={reason}
              maxLength={2000}
              required
              disabled={busy}
              onChange={(e) => {
                change();
                setReason(e.target.value);
              }}
            />
          </div>
          {(action === "edit" || action === "merge") && (
            <div className="extraction-field review-form-wide">
              <label htmlFor="review-replacement">
                {action === "edit"
                  ? "Full replacements JSON array (extraction_id, payload, evidence)"
                  : "Explicit merge source JSON (payload_source_id)"}
              </label>
              <textarea
                id="review-replacement"
                className="extraction-control extraction-code"
                rows={12}
                value={patch}
                required
                disabled={busy}
                onChange={(e) => {
                  change();
                  setPatch(e.target.value);
                }}
              />
              <p className="extraction-hint">
                Provide the complete strict payload and evidence for every edit. Candidate display
                fields are never converted automatically. A merge copies the selected source; it
                does not sum values.
              </p>
            </div>
          )}
          <button
            type="submit"
            className="extraction-button extraction-button-primary review-form-submit"
            disabled={
              busy ||
              stale ||
              !permitted ||
              !selected.length ||
              selected.length > 100 ||
              !editable ||
              !reason.trim()
            }
          >
            Submit atomic review
          </button>
          {!permitted && (
            <p className="extraction-hint review-form-wide">
              Your current permissions do not allow this action.
            </p>
          )}
        </form>
      </section>
      {compared && (
        <section className="extraction-card">
          <h2>Refreshed selected versions</h2>
          {selected.map((p) => (
            <div key={p.id} className="review-compared">
              <h3>
                <span className="extraction-mono">{p.id}</span> · v{p.version} ·{" "}
                <StatusBadge status={p.state} />
              </h3>
              <PayloadFields payload={p.payload} />
            </div>
          ))}
          <button
            type="button"
            className="extraction-button extraction-button-primary"
            onClick={() => {
              setStale(false);
              setCompared(false);
              change();
              setMessage("Refreshed versions selected. Submit intentionally when ready.");
            }}
          >
            Use refreshed versions
          </button>
        </section>
      )}
      <p role="status" aria-live="polite" className="extraction-status">
        {message}
      </p>
      {result && (
        <section aria-label="Immutable review receipt" className="extraction-card">
          <h2>Review receipt</h2>
          <p className="extraction-mono">Review {result.review_id}</p>
          <ul>
            {result.approved_versions.map((v) => (
              <li key={v.version_id}>
                <Link href={`/approved-extractions/${v.record_id}/versions/${v.version_id}`}>
                  Approved version {v.version}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}
