import Link from "next/link";
import type { Schemas } from "../../lib/extraction/contracts";
import { getEvidenceSource } from "../../lib/data/server";
import { RunLink, StatusBadge, Timestamp, humanize } from "./labels";

export async function SourceLinks({
  evidence,
  sources,
}: {
  evidence: Schemas["EvidenceEdge"][];
  sources: { run_id: string; as_of: string; corpus_version_id?: string }[] | null;
}) {
  if (!sources)
    return (
      <section aria-label="Historical source context" className="extraction-card">
        <h2>Historical source context</h2>
        <p>
          Unknown: this historical version has no recorded validation context. No current cutoff was
          substituted.
        </p>
        <ul className="extraction-list">
          {evidence.map((e, i) => (
            <li key={i}>
              Span {e.source_span_id} · Parsed version {e.document_version_id}
            </li>
          ))}
        </ul>
      </section>
    );
  let references: Awaited<
    ReturnType<ReturnType<typeof getEvidenceSource>["resolveDocumentVersions"]>
  > = [];
  const source = sources.length === 1 ? sources[0] : undefined;
  if (source && evidence.length) {
    try {
      references = await getEvidenceSource().resolveDocumentVersions(
        [...new Set(evidence.map((e) => e.document_version_id))],
        { asOf: source.as_of, corpusVersionId: source.corpus_version_id ?? null },
      );
    } catch {
      /* Pins remain visible; unavailable evidence never gains an invented link. */
    }
  }
  return (
    <section aria-label="Frozen evidence provenance" className="extraction-card">
      <h2>Source context</h2>
      <ul className="extraction-list">
        {sources.map((s) => (
          <li key={s.run_id}>
            <RunLink id={s.run_id} prefix="Source run" /> · Cutoff <Timestamp value={s.as_of} /> ·
            Corpus{" "}
            <span className="extraction-mono">
              {s.corpus_version_id ?? "No corpus pin recorded"}
            </span>
          </li>
        ))}
      </ul>
      {sources.length > 1 && (
        <p>
          This version combines multiple source contexts. Follow the immutable source runs to
          inspect their respective cutoffs and corpora.
        </p>
      )}
      {!evidence.length && <p>No evidence edges recorded.</p>}
      <ul className="extraction-list">
        {evidence.map((edge, index) => {
          const reference = references.find(
            (r) => r.document_version_id === edge.document_version_id,
          );
          const query =
            source &&
            new URLSearchParams({
              as_of: source.as_of,
              // Empty explicitly overrides a configured reader corpus. Omitting
              // this key would substitute today's deployment pin for history.
              corpus_version_id: source.corpus_version_id ?? "",
              document_version_id: edge.document_version_id,
              span: edge.source_span_id,
            });
          return (
            <li key={index}>
              {humanize(edge.role)} · <StatusBadge status={edge.citation_status} /> ·{" "}
              {reference && query ? (
                <Link href={`/reader/${reference.document_id}?${query}`}>
                  Read evidence span {edge.source_span_id}
                </Link>
              ) : (
                <>
                  Span {edge.source_span_id} · Parsed version {edge.document_version_id}
                </>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
