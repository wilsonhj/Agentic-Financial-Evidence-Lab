import Link from "next/link";
import type { ReactNode } from "react";
import type { Proposal } from "../../lib/extraction/contracts";
import { StatusBadge, humanize } from "./labels";
import "../../styles/extraction.css";

export function ExtractionShell({
  title,
  mode,
  children,
}: {
  title: string;
  mode?: "fixture" | "http";
  children: ReactNode;
}) {
  return (
    <main id="main-content" className="page-main extraction-page" tabIndex={-1}>
      <nav aria-label="Extraction navigation" className="extraction-nav">
        <Link href="/desk">Desk</Link>
        <Link href="/extractions">Review queue</Link>
        <Link href="/extraction-runs">Run history</Link>
      </nav>
      <h1 className="extraction-title">{title}</h1>
      {mode === "fixture" && (
        <p role="note" className="extraction-note">
          Synthetic fixture mode. These examples do not establish financial validity or live
          execution.
        </p>
      )}
      {children}
    </main>
  );
}
export function PayloadFields({ payload }: { payload: Proposal["payload"] }) {
  const candidate = payload.schema_version === "extraction-candidate-fields/v1";
  const fields = candidate ? payload.fields : payload;
  return (
    <section aria-label="Financial fields" className="extraction-card">
      <h2>{candidate ? "Read-only candidate fields" : "Recorded financial fields"}</h2>
      {candidate && (
        <p>
          Persisted JSON text. Missing fields are absent; the text null represents a present JSON
          null. Full edits require an explicit strict replacement.
        </p>
      )}
      <dl className="extraction-fields">
        {Object.entries(fields).map(([name, value]) => (
          <div key={name}>
            <dt>{name}</dt>
            <dd>
              <pre>
                {candidate
                  ? value
                  : typeof value === "string"
                    ? value
                    : JSON.stringify(value, null, 2)}
              </pre>
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
export function ProposalStatus({ proposal }: { proposal: Proposal }) {
  return (
    <section aria-label="Validation and confidence" className="extraction-card">
      <h2>Validation and confidence</h2>
      <dl className="extraction-meta">
        <div>
          <dt>State</dt>
          <dd>
            <StatusBadge status={proposal.state} />
          </dd>
        </div>
        <div>
          <dt>Version</dt>
          <dd className="extraction-num">{proposal.version}</dd>
        </div>
        <div>
          <dt>Priority</dt>
          <dd>
            {proposal.review_priority === "high" ? (
              <StatusBadge status="warning" label="High" />
            ) : (
              humanize(proposal.review_priority)
            )}
          </dd>
        </div>
        <div>
          <dt>Record confidence</dt>
          <dd className="extraction-num">{proposal.record_confidence ?? "Uncalibrated"}</dd>
        </div>
      </dl>
      {Object.keys(proposal.field_confidences).length > 0 && (
        <>
          <h3>Field confidence</h3>
          <dl className="extraction-meta">
            {Object.entries(proposal.field_confidences).map(([field, score]) => (
              <div key={field}>
                <dt>{field}</dt>
                <dd className="extraction-num">{score}</dd>
              </div>
            ))}
          </dl>
        </>
      )}
      {proposal.validations.length > 0 && (
        <>
          <h3>Validations</h3>
          <ul className="extraction-validations">
            {proposal.validations.map((v, index) => (
              <li key={`${v.code}-${index}`}>
                <StatusBadge status={v.status} label={`${v.status}: ${v.code}`} />
              </li>
            ))}
          </ul>
        </>
      )}
      {!proposal.validations.length && <p>No validation results recorded.</p>}
      {!proposal.evidence.length && (
        <p role="note" className="extraction-note extraction-note-warning">
          <span aria-hidden="true">{"\u26A0"}</span> No evidence edges recorded. Approval still
          requires verified evidence.
        </p>
      )}
    </section>
  );
}
export function ExtractionPagination({
  path,
  query = {},
  page,
}: {
  path: string;
  query?: Record<string, string>;
  page: { next_cursor: string | null; previous_cursor: string | null; limit: number };
}) {
  const link = (cursor: string) =>
    `${path}?${new URLSearchParams({ ...query, limit: String(page.limit), cursor })}`;
  return (
    <nav aria-label="Extraction pages" className="extraction-pagination">
      {page.previous_cursor ? (
        <Link className="extraction-button" href={link(page.previous_cursor)}>
          Previous page
        </Link>
      ) : (
        <span className="extraction-button" aria-disabled="true">
          Previous page
        </span>
      )}
      {page.next_cursor ? (
        <Link className="extraction-button" href={link(page.next_cursor)}>
          Next page
        </Link>
      ) : (
        <span className="extraction-button" aria-disabled="true">
          Next page
        </span>
      )}
    </nav>
  );
}
export function ExtractionError() {
  return (
    <section role="alert" className="extraction-card extraction-alert">
      <h2>Extraction view unavailable</h2>
      <p>
        Check the selected source configuration, your access and the requested scope. No fixture
        fallback was used.
      </p>
      <Link href="/extractions">Return to review queue</Link>
    </section>
  );
}
