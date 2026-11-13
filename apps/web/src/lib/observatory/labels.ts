/**
 * Display-only labels for Observatory enums and codes. The raw code stays the
 * source of truth (form values, URLs, data attributes and `title` tooltips keep
 * it); these helpers only decide what a reader sees.
 */

const CODE_LABELS: Record<string, string> = {
  // Plan intents
  fact_lookup: "Fact lookup",
  // Candidate rejection / decision codes
  temporal_after_cutoff: "Published after cutoff",
  cross_version: "Different document version",
  dedupe_near_duplicate: "Near-duplicate",
  context_budget_selected: "Selected for context",
  insufficient_support: "Insufficient support",
  rejected: "Rejected",
  // Claim and citation verdicts
  partially_supported: "Partially supported",
  // Candidate kinds
  table_row: "Table row",
};

/**
 * Human label for an enum value or reason code: a known override, otherwise
 * the code with underscores as spaces and an initial capital
 * (`run_started` → "Run started").
 */
export function humanizeCode(code: string): string {
  const known = CODE_LABELS[code];
  if (known) return known;
  const spaced = code.replace(/[_-]+/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Leading 8 characters of a UUID, as used for short run/item references. */
export function shortId(id: string): string {
  return id.slice(0, 8);
}

/**
 * Compact UTC rendering of an ISO timestamp ("2026-06-30 23:59 UTC"); seconds
 * and milliseconds are kept only when they are not zero, so closely spaced
 * events stay distinguishable. Unparseable input is returned as is.
 */
export function formatUtc(iso: string): string {
  const time = Date.parse(iso);
  if (Number.isNaN(time)) return iso;
  const full = new Date(time).toISOString(); // YYYY-MM-DDTHH:mm:ss.sssZ
  const date = full.slice(0, 10);
  const end = full.slice(20, 23) !== "000" ? 23 : full.slice(17, 19) !== "00" ? 19 : 16;
  return `${date} ${full.slice(11, end)} UTC`;
}

/** Minimal candidate shape the display helpers need. */
interface CandidateLike {
  item_id: string;
  kind: string;
  fused_rank?: number | null;
}

/**
 * Distinguishing reader-facing name for a candidate. Item ids in a run often
 * share their leading characters, so the fused rank (unique within a run) is
 * used when present: "Passage, fused rank 1". Falls back to the short id.
 */
export function candidateLabel(candidate: CandidateLike): string {
  const kind = humanizeCode(candidate.kind);
  return candidate.fused_rank != null
    ? `${kind}, fused rank ${candidate.fused_rank}`
    : `${kind} ${shortId(candidate.item_id)}`;
}
