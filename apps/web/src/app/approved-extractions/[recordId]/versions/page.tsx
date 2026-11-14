import Link from "next/link";
import { getExtractionSource } from "../../../../lib/extraction/source";
import { guards } from "../../../../lib/extraction/contracts";
import { pageQuery } from "../../../../lib/extraction/page-query";
import {
  ExtractionShell,
  ExtractionError,
  ExtractionPagination,
} from "../../../../components/extraction/display";
import { Timestamp } from "../../../../components/extraction/labels";
export const dynamic = "force-dynamic";
export default async function VersionsPage({
  params,
  searchParams,
}: {
  params: Promise<{ recordId: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  try {
    const source = getExtractionSource(),
      { recordId } = await params,
      query = pageQuery(await searchParams);
    const { data: page } = await source.read(
      `approved/${recordId}/versions`,
      guards.versions,
      query,
    );
    return (
      <ExtractionShell title="Immutable approval history" mode={source.mode}>
        <p className="extraction-lede">
          <Link href={`/approved-extractions/${recordId}`}>
            Current approved head and correction
          </Link>
        </p>
        {!page.items.length ? (
          <p className="extraction-empty">No versions on this page.</p>
        ) : (
          <div
            className="extraction-table-scroll"
            role="region"
            aria-label="Immutable versions, scrollable"
            tabIndex={0}
          >
            <table className="extraction-table">
              <caption>Immutable versions</caption>
              <thead>
                <tr>
                  <th scope="col">Version</th>
                  <th scope="col">Approved at</th>
                  <th scope="col">Reason</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((v) => (
                  <tr key={v.version_id}>
                    <td className="extraction-nowrap">
                      <Link href={`/approved-extractions/${recordId}/versions/${v.version_id}`}>
                        Version {v.version}
                      </Link>
                    </td>
                    <td className="extraction-nowrap">
                      <Timestamp value={v.created_at} />
                    </td>
                    <td>{v.approval_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <ExtractionPagination
          path={`/approved-extractions/${recordId}/versions`}
          query={Object.fromEntries(query)}
          page={page}
        />
      </ExtractionShell>
    );
  } catch {
    return (
      <ExtractionShell title="Immutable approval history">
        <ExtractionError />
      </ExtractionShell>
    );
  }
}
