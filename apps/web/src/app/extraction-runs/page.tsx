import { getExtractionSource } from "../../lib/extraction/source";
import { guards } from "../../lib/extraction/contracts";
import { pageQuery } from "../../lib/extraction/page-query";
import {
  ExtractionShell,
  ExtractionError,
  ExtractionPagination,
} from "../../components/extraction/display";
import { ActionForm } from "../../components/extraction/ActionForm";
import { RunLink, StatusBadge, Timestamp } from "../../components/extraction/labels";
export const dynamic = "force-dynamic";
export default async function RunsPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  try {
    const source = getExtractionSource(),
      query = pageQuery(await searchParams);
    const [page, permissions] = await Promise.all([
      source.read("runs", guards.runs, query),
      source.read("permissions", guards.permissions),
    ]);
    return (
      <ExtractionShell title="Extraction runs" mode={source.mode}>
        <p className="extraction-lede">
          Runs retain their original evidence, corpus, cutoff and workflow pins.
        </p>
        {!page.data.items.length ? (
          <p className="extraction-empty">No runs on this page.</p>
        ) : (
          <div
            className="extraction-table-scroll"
            role="region"
            aria-label="Run history, scrollable"
            tabIndex={0}
          >
            <table className="extraction-table">
              <caption>Run history</caption>
              <thead>
                <tr>
                  <th scope="col">Run</th>
                  <th scope="col">Status</th>
                  <th scope="col">Cutoff</th>
                  <th scope="col">Provider</th>
                  <th scope="col" className="extraction-num">
                    Cost USD
                  </th>
                </tr>
              </thead>
              <tbody>
                {page.data.items.map((run) => (
                  <tr key={run.id}>
                    <td className="extraction-nowrap">
                      <RunLink id={run.id} />
                    </td>
                    <td>
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="extraction-nowrap">
                      <Timestamp value={run.as_of} />
                    </td>
                    <td>{run.provider}</td>
                    <td className="extraction-num">{run.usage.cost_usd}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <ExtractionPagination
          path="/extraction-runs"
          query={Object.fromEntries(query)}
          page={page.data}
        />
        <ActionForm
          action="create"
          path="runs"
          permitted={permissions.data.allowed_actions.includes("create")}
        />
      </ExtractionShell>
    );
  } catch {
    return (
      <ExtractionShell title="Extraction runs">
        <ExtractionError />
      </ExtractionShell>
    );
  }
}
