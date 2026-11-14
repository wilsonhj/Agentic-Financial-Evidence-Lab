import Link from "next/link";
import { getExtractionSource } from "../../lib/extraction/source";
import { guards } from "../../lib/extraction/contracts";
import { pageQuery } from "../../lib/extraction/page-query";
import {
  ExtractionShell,
  ExtractionError,
  ExtractionPagination,
} from "../../components/extraction/display";
import { ReviewQueue } from "../../components/extraction/ReviewQueue";
import { humanize } from "../../components/extraction/labels";
export const dynamic = "force-dynamic";
export default async function ExtractionsPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  try {
    const source = getExtractionSource(),
      query = pageQuery(await searchParams);
    if (!query.has("state")) query.set("state", "needs_review");
    const [page, permissions] = await Promise.all([
      source.read("proposals", guards.proposals, query),
      source.read("permissions", guards.permissions),
    ]);
    return (
      <ExtractionShell title="Extraction review" mode={source.mode}>
        <p className="extraction-lede">
          Inspect evidence and deterministic validation before approving an immutable financial
          record.
        </p>
        <form method="get" className="extraction-filter">
          <div className="extraction-field">
            <label htmlFor="queue-state">State</label>
            <select
              name="state"
              id="queue-state"
              className="extraction-control"
              defaultValue={query.get("state") ?? "needs_review"}
            >
              {["proposed", "needs_review", "accepted", "rejected", "superseded"].map((s) => (
                <option key={s} value={s}>
                  {humanize(s)}
                </option>
              ))}
            </select>
          </div>
          <button type="submit" className="extraction-button">
            Filter queue
          </button>
        </form>
        <ReviewQueue
          key={query.toString()}
          proposals={page.data.items}
          permissions={permissions.data}
        />
        <ExtractionPagination
          path="/extractions"
          query={Object.fromEntries(query)}
          page={page.data}
        />
        {source.mode === "fixture" && (
          <p className="extraction-footer-link">
            <Link href="/approved-extractions/eeeeeeee-0000-4000-8000-000000000007">
              Inspect synthetic immutable approval history
            </Link>
          </p>
        )}
      </ExtractionShell>
    );
  } catch {
    return (
      <ExtractionShell title="Extraction review">
        <ExtractionError />
      </ExtractionShell>
    );
  }
}
