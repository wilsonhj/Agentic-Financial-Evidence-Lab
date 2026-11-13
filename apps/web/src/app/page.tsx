import Link from "next/link";

import { EvidenceFailureState } from "../components/EvidenceFailureState";
import { PageNavigation } from "../components/PageNavigation";
import { evidenceFailureState } from "../lib/data/failure-state";
import { getEvidenceSource } from "../lib/data/server";
import { formatPeriodRange } from "../lib/document-display";
import "../styles/filings.css";

export const dynamic = "force-dynamic";

/** The page data carries entity IDs only (no names), so show a labelled short ID. */
const entityLabel = (id: string) => `Entity ${id.slice(0, 8)}…`;

export default async function DocumentListPage({
  searchParams,
}: {
  searchParams?: Promise<{ entity?: string; cursor?: string; order?: "asc" | "desc" }>;
}) {
  const search = (await searchParams) ?? {};
  let page;
  let entityIds: readonly string[];
  let entityId: string;
  try {
    const source = getEvidenceSource();
    entityIds = source.entityIds;
    entityId = search.entity ?? entityIds[0] ?? "";
    page = await source.listDocuments(entityId, {
      limit: 50,
      cursor: search.cursor,
      order: search.order ?? "asc",
    });
  } catch (error) {
    const kind = evidenceFailureState(error);
    if (kind) return <EvidenceFailureState kind={kind} />;
    throw error;
  }
  const documents = page.items;

  return (
    <main id="main-content" tabIndex={-1} className="page-main" aria-labelledby="documents-heading">
      <h2 id="documents-heading">Filings</h2>
      <p>Select a filing to open its version-pinned evidence snapshot.</p>
      <form action="/" className="filings-picker">
        <label htmlFor="filing-entity">Entity</label>
        <select id="filing-entity" name="entity" defaultValue={entityId}>
          {entityIds.map((id) => (
            <option key={id} value={id} title={id}>
              {entityLabel(id)}
            </option>
          ))}
        </select>
        <button type="submit">Show filings</button>
      </form>
      <PageNavigation
        path="/"
        params={{ entity: entityId }}
        nextCursor={page.nextCursor}
        previousCursor={page.previousCursor}
        order={search.order ?? "asc"}
        label="Filing pages"
      />
      <div className="filings-note">
        <p>Showing {documents.length} filings.</p>
        <p className="filings-caveat">
          <span aria-hidden="true">&#8505;</span>
          <span>Note: Amendment history is not fully loaded.</span>
        </p>
      </div>
      <div
        className="filings-table-scroll"
        role="region"
        aria-labelledby="documents-heading"
        tabIndex={0}
      >
        <table className="doc-table">
          <caption className="visually-hidden" title={entityId}>
            Filings for {entityLabel(entityId)}
          </caption>
          <thead>
            <tr>
              <th scope="col">Form</th>
              <th scope="col">Accession</th>
              <th scope="col">Period</th>
              <th scope="col">Published</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => {
              const amended = doc.form?.endsWith("/A");
              return (
                <tr key={doc.id}>
                  <td>
                    <Link href={`/reader/${doc.id}`}>{doc.form ?? "Filing"}</Link>
                  </td>
                  <td className="filings-num">
                    {doc.accession}
                    {/^https?:\/\//i.test(doc.source_url) && (
                      <>
                        {" "}
                        · <a href={doc.source_url}>Original filing</a>
                      </>
                    )}
                  </td>
                  <td className="filings-num">{formatPeriodRange(doc)}</td>
                  <td className="filings-num">{doc.published_at.slice(0, 10)}</td>
                  <td>
                    <span className={amended ? "badge badge-warning" : "badge badge-info"}>
                      <span aria-hidden="true">{amended ? "⚠" : "ℹ"}</span>{" "}
                      {amended ? "Amendment / restatement" : "History not loaded"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </main>
  );
}
