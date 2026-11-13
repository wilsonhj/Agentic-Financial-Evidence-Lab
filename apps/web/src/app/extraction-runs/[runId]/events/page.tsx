import { getExtractionSource } from "../../../../lib/extraction/source";
import { guards } from "../../../../lib/extraction/contracts";
import { pageQuery } from "../../../../lib/extraction/page-query";
import {
  ExtractionShell,
  ExtractionError,
  ExtractionPagination,
} from "../../../../components/extraction/display";
import { RunLink, Timestamp } from "../../../../components/extraction/labels";
export const dynamic = "force-dynamic";
export default async function EventHistoryPage({
  params,
  searchParams,
}: {
  params: Promise<{ runId: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  try {
    const source = getExtractionSource(),
      { runId } = await params,
      query = pageQuery(await searchParams);
    const { data: page } = await source.read(`runs/${runId}/event-history`, guards.events, query);
    return (
      <ExtractionShell title="Stored extraction events" mode={source.mode}>
        <p className="extraction-lede">
          <RunLink id={runId} />. This bounded page is stored history.
        </p>
        {!page.items.length ? (
          <p className="extraction-empty">No events on this page.</p>
        ) : (
          <div
            className="extraction-table-scroll"
            role="region"
            aria-label="Persisted events, scrollable"
            tabIndex={0}
          >
            <table className="extraction-table">
              <caption>Persisted events in order</caption>
              <thead>
                <tr>
                  <th scope="col" className="extraction-num">
                    ID
                  </th>
                  <th scope="col">Type</th>
                  <th scope="col">Time</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((e) => (
                  <tr key={e.id}>
                    <td className="extraction-num">{e.id}</td>
                    <td className="extraction-mono">{e.type}</td>
                    <td className="extraction-nowrap">
                      <Timestamp value={e.occurred_at} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <ExtractionPagination
          path={`/extraction-runs/${runId}/events`}
          query={Object.fromEntries(query)}
          page={page}
        />
      </ExtractionShell>
    );
  } catch {
    return (
      <ExtractionShell title="Stored extraction events">
        <ExtractionError />
      </ExtractionShell>
    );
  }
}
