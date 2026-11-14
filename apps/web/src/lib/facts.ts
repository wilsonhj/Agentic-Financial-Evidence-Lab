import type { AmendmentLink } from "./amendments";
import type { FinancialFactRecord, NormalizedFinancialFact } from "./contracts";

/**
 * String-only decimal arithmetic: monetary values are decimal strings and are
 * never routed through binary floats (spec 11.4). `scaledDecimal` applies the
 * fact's power-of-ten scale by shifting the decimal point.
 */
export function scaledDecimal(value: string, scale: number): string {
  const match = /^(-?)([0-9]+)(?:\.([0-9]+))?$/.exec(value);
  if (!match) {
    throw new Error(`Not a decimal string: ${JSON.stringify(value)}`);
  }
  const sign = match[1] === "-" ? "-" : "";
  const intPart = match[2] ?? "0";
  const fracPart = match[3] ?? "";
  const digits = intPart + fracPart;
  const pointPos = intPart.length + scale;

  let result: string;
  if (pointPos >= digits.length) {
    result = digits + "0".repeat(pointPos - digits.length);
  } else if (pointPos <= 0) {
    result = `0.${"0".repeat(-pointPos)}${digits}`;
  } else {
    result = `${digits.slice(0, pointPos)}.${digits.slice(pointPos)}`;
  }

  // Canonicalize: strip leading zeros, trailing fractional zeros, and -0.
  let [int = "0", frac = ""] = result.split(".");
  int = int.replace(/^0+(?=[0-9])/, "");
  frac = frac.replace(/0+$/, "");
  const canonical = frac.length > 0 ? `${int}.${frac}` : int;
  return canonical === "0" ? "0" : sign + canonical;
}

/** Groups digits for display (string-based; no float round-trip). */
export function formatScaledValue(fact: NormalizedFinancialFact): string {
  const canonical = scaledDecimal(fact.value, fact.scale);
  const [intPart = "0", fracPart] = canonical.replace(/^-/, "").split(".");
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const sign = canonical.startsWith("-") ? "-" : "";
  return sign + grouped + (fracPart ? `.${fracPart}` : "");
}

function periodKey(period: NormalizedFinancialFact["period"]): string {
  return period.type === "instant"
    ? `instant:${period.instant ?? ""}`
    : `duration:${period.start ?? ""}..${period.end ?? ""}`;
}

function dimensionsKey(dimensions: Record<string, string> | undefined): string {
  const entries = Object.entries(dimensions ?? {}).sort(([a], [b]) => a.localeCompare(b));
  return entries.map(([k, v]) => `${k}=${v}`).join("&");
}

/**
 * Two facts are duplicates when they assert the same concept for the same
 * entity, period, unit, and dimensions. Value and scale are deliberately
 * excluded: duplicates with different canonical values are the conflicts the
 * reader must flag.
 */
export function factIdentityKey(fact: NormalizedFinancialFact): string {
  return [
    fact.entity_id,
    fact.concept,
    fact.unit,
    periodKey(fact.period),
    dimensionsKey(fact.dimensions),
  ].join("|");
}

export interface DuplicateFactGroup {
  key: string;
  records: FinancialFactRecord[];
  /** Distinct canonical (scale-applied) values across the group. */
  canonicalValues: string[];
  status: "consistent" | "conflicting";
}

/** Groups duplicated facts and flags groups whose canonical values disagree. */
export function groupDuplicateFacts(records: readonly FinancialFactRecord[]): DuplicateFactGroup[] {
  const groups = new Map<string, FinancialFactRecord[]>();
  for (const record of records) {
    const key = factIdentityKey(record.fact);
    const bucket = groups.get(key);
    if (bucket) bucket.push(record);
    else groups.set(key, [record]);
  }
  const result: DuplicateFactGroup[] = [];
  for (const [key, bucket] of groups) {
    if (bucket.length < 2) continue;
    const canonicalValues = [
      ...new Set(bucket.map((record) => scaledDecimal(record.fact.value, record.fact.scale))),
    ];
    result.push({
      key,
      records: bucket,
      canonicalValues,
      status: canonicalValues.length > 1 ? "conflicting" : "consistent",
    });
  }
  return result;
}

/** Lookup: fact record id -> its duplicate group (only ids that are in a group). */
export function duplicateGroupIndex(
  groups: readonly DuplicateFactGroup[],
): Map<string, DuplicateFactGroup> {
  const index = new Map<string, DuplicateFactGroup>();
  for (const group of groups) {
    for (const record of group.records) {
      index.set(record.id, group);
    }
  }
  return index;
}

/** Distinct canonical values per filing (DocumentMeta.id) within one group. */
function valuesByDocument(
  group: DuplicateFactGroup,
  documentIdBySpanId: Readonly<Record<string, string>>,
): Map<string, Set<string>> {
  const byDoc = new Map<string, Set<string>>();
  for (const record of group.records) {
    const docId = documentIdBySpanId[record.fact.source_span_id];
    if (!docId) continue;
    const values = byDoc.get(docId) ?? new Set<string>();
    values.add(scaledDecimal(record.fact.value, record.fact.scale));
    byDoc.set(docId, values);
  }
  return byDoc;
}

/**
 * True when an amendment reports a different canonical value than the filing
 * it amends — i.e. the fact was actually restated, not merely repeated.
 */
export function isRestatementGroup(
  group: DuplicateFactGroup,
  documentIdBySpanId: Readonly<Record<string, string>>,
  amendmentLinks: readonly AmendmentLink[],
): boolean {
  const byDoc = valuesByDocument(group, documentIdBySpanId);
  return amendmentLinks.some((link) => {
    const original = byDoc.get(link.originalId);
    const amended = byDoc.get(link.amendmentId);
    if (!original || !amended) return false;
    return [...amended].some((value) => !original.has(value));
  });
}

/**
 * How a conflicting group should be presented. `restatement` means every
 * difference is explained by an amendment: each filing reports one value and
 * an amendment changed it. Anything else — two values inside one filing, or
 * differences between unrelated filings — stays a `conflict`, even when an
 * amendment is also involved.
 */
export function conflictKind(
  group: DuplicateFactGroup,
  documentIdBySpanId: Readonly<Record<string, string>>,
  amendmentLinks: readonly AmendmentLink[],
): "restatement" | "conflict" {
  if (!isRestatementGroup(group, documentIdBySpanId, amendmentLinks)) return "conflict";
  const byDoc = valuesByDocument(group, documentIdBySpanId);
  if ([...byDoc.values()].some((values) => values.size > 1)) return "conflict";
  // Every pair of filings that disagree must belong to one amendment chain
  // (original -> amendment 1 -> amendment 2 ...); otherwise the disagreement is
  // not explained by a restatement. Links are successive, so connectivity is
  // checked through the whole chain, not just direct edges.
  const root = new Map<string, string>();
  const find = (id: string): string => {
    let current = id;
    while (root.has(current) && root.get(current) !== current) current = root.get(current)!;
    return current;
  };
  for (const link of amendmentLinks) {
    const a = find(link.originalId);
    const b = find(link.amendmentId);
    root.set(a, a);
    if (a !== b) root.set(b, a);
  }
  const docs = [...byDoc.keys()];
  for (let i = 0; i < docs.length; i += 1) {
    for (let j = i + 1; j < docs.length; j += 1) {
      const a = docs[i]!;
      const b = docs[j]!;
      const [va] = byDoc.get(a)!;
      const [vb] = byDoc.get(b)!;
      if (va !== vb && find(a) !== find(b)) return "conflict";
    }
  }
  return "restatement";
}
