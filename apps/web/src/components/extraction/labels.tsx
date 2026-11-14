import Link from "next/link";

/**
 * Display-only helpers for the extraction area. Raw contract values stay the
 * submitted form values, URLs and data; these only change what is shown.
 */

const LABELS: Record<string, string> = {
  needs_review: "Needs review",
  waiting_review: "Waiting for review",
  revenue_driver: "Revenue driver",
  kpi: "KPI",
};

/** `needs_review` → "Needs review". Unknown codes are humanized, never dropped. */
export function humanize(value: string): string {
  const known = LABELS[value];
  if (known) return known;
  const words = value.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** First UUID segment, e.g. `eeeeeeee`, for compact identifiers. */
export function shortId(id: string): string {
  return id.split("-")[0] || id;
}

/** `2026-07-01T00:00:00Z` → `2026-07-01 00:00:00 UTC`; anything else is shown verbatim. */
export function formatTimestamp(iso: string): string {
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.\d+)?Z$/.exec(iso);
  return match ? `${match[1]} ${match[2]} UTC` : iso;
}

export function Timestamp({ value }: { value: string }) {
  return <time dateTime={value}>{formatTimestamp(value)}</time>;
}

type Tone = "ok" | "warning" | "info" | "neutral";

const TONES: Record<string, Tone> = {
  // Proposal states
  proposed: "info",
  needs_review: "info",
  accepted: "ok",
  rejected: "neutral",
  superseded: "neutral",
  // Run and step statuses
  queued: "info",
  pending: "info",
  claimed: "info",
  running: "info",
  waiting_review: "info",
  succeeded: "ok",
  failed: "warning",
  cancelled: "neutral",
  skipped: "neutral",
  // Conflict group statuses
  open: "warning",
  resolved: "ok",
  // Evidence citation statuses
  verified: "ok",
  partial: "warning",
  contradictory: "warning",
  invalid: "warning",
  // Validation statuses
  pass: "ok",
  warning: "warning",
  fail: "warning",
};

/* Glyph + text always accompany the colour (never colour alone). */
const GLYPHS: Record<Tone, string> = {
  ok: "✓",
  warning: "⚠",
  info: "●",
  neutral: "–",
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const tone = TONES[status] ?? "info";
  const className = tone === "neutral" ? "badge" : `badge badge-${tone}`;
  const text = label ?? humanize(status);
  const content = (
    <>
      <span aria-hidden="true">{GLYPHS[tone]}</span> {text}
    </>
  );
  return tone === "warning" ? (
    <strong className={`${className} extraction-badge`}>{content}</strong>
  ) : (
    <span className={`${className} extraction-badge`}>{content}</span>
  );
}

/** Short run link ("Run eeeeeeee") with the full immutable ID in `title`. */
export function RunLink({ id, prefix = "Run" }: { id: string; prefix?: string }) {
  return (
    <Link href={`/extraction-runs/${id}`} title={id}>
      {prefix} {shortId(id)}
    </Link>
  );
}
