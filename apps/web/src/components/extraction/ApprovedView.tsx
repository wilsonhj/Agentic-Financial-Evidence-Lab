import Link from "next/link";
import type { Approved } from "../../lib/extraction/contracts";
import { PayloadFields } from "./display";
import { SourceLinks } from "./SourceLinks";
import { Timestamp } from "./labels";
export function ApprovedView({ approved }: { approved: Approved }) {
  return (
    <>
      <section aria-label="Approval record" className="extraction-card">
        <p className="extraction-reason">Reason: {approved.approval_reason}</p>
        <dl className="extraction-meta">
          <div>
            <dt>Immutable version</dt>
            <dd>
              <span className="extraction-num">{approved.version}</span>{" "}
              <span className="extraction-mono extraction-muted">{approved.version_id}</span>
            </dd>
          </div>
          <div>
            <dt>Approved by</dt>
            <dd className="extraction-mono">{approved.approved_by}</dd>
          </div>
          <div>
            <dt>Approved at</dt>
            <dd>
              <Timestamp value={approved.created_at} />
            </dd>
          </div>
          <div>
            <dt>Pipeline versions</dt>
            <dd>
              {approved.ontology_version} · {approved.normalizer_version} ·{" "}
              {approved.validator_version}
            </dd>
          </div>
          <div className="extraction-meta-wide">
            <dt>Evidence manifest</dt>
            <dd className="extraction-mono">{approved.evidence_manifest_hash}</dd>
          </div>
        </dl>
        {approved.parent_version_id && (
          <p>
            <Link
              href={`/approved-extractions/${approved.record_id}/versions/${approved.parent_version_id}`}
            >
              Previous immutable version
            </Link>
          </p>
        )}
      </section>
      <PayloadFields payload={approved.payload} />
      <SourceLinks
        evidence={approved.evidence}
        sources={approved.validation_context?.source_runs ?? null}
      />
    </>
  );
}
