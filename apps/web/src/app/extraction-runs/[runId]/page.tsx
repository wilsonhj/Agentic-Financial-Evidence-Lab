import Link from "next/link";
import { getExtractionSource } from "../../../lib/extraction/source";
import { guards } from "../../../lib/extraction/contracts";
import { pageQuery } from "../../../lib/extraction/page-query";
import {
  ExtractionShell,
  ExtractionError,
  ExtractionPagination,
} from "../../../components/extraction/display";
import { ActionForm } from "../../../components/extraction/ActionForm";
import { RunEvents } from "../../../components/extraction/RunEvents";
import { StatusBadge, Timestamp, humanize, shortId } from "../../../components/extraction/labels";
export const dynamic = "force-dynamic";
export default async function RunPage({
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
    const [run, steps, permissions] = await Promise.all([
      source.read(`runs/${runId}`, guards.run),
      source.read(`runs/${runId}/steps`, guards.steps, query),
      source.read("permissions", guards.permissions),
    ]);
    const r = run.data;
    return (
      <ExtractionShell title={`Extraction run ${shortId(r.id)}`} mode={source.mode}>
        <p className="extraction-lede extraction-links">
          <Link href="/extractions">Browse workspace review queue</Link>
          <Link href={`/extraction-runs/${r.id}/events`}>Stored event history</Link>
          {r.parent_run_id && (
            <Link href={`/extraction-runs/${r.parent_run_id}`} title={r.parent_run_id}>
              Original parent run
            </Link>
          )}
        </p>
        <section aria-label="Run summary" className="extraction-card">
          <dl className="extraction-meta">
            <div>
              <dt>Status</dt>
              <dd>
                <StatusBadge status={r.status} />
              </dd>
            </div>
            <div>
              <dt>Cutoff</dt>
              <dd>
                <Timestamp value={r.as_of} />
              </dd>
            </div>
            <div>
              <dt>Provider / model</dt>
              <dd>
                {r.provider} / {r.model}
              </dd>
            </div>
            <div>
              <dt>Workflow · ontology</dt>
              <dd>
                {r.workflow_version} · {r.ontology_version}
              </dd>
            </div>
            <div>
              <dt>Usage</dt>
              <dd className="extraction-num">
                {r.usage.calls} calls · {r.usage.input_tokens} input tokens ·{" "}
                {r.usage.output_tokens} output tokens
              </dd>
            </div>
            <div>
              <dt>Cost</dt>
              <dd className="extraction-num">USD {r.usage.cost_usd}</dd>
            </div>
            <div className="extraction-meta-wide">
              <dt>Run ID</dt>
              <dd className="extraction-mono">{r.id}</dd>
            </div>
            <div className="extraction-meta-wide">
              <dt>Corpus</dt>
              <dd className="extraction-mono">{r.corpus_version_id ?? "No corpus pin recorded"}</dd>
            </div>
            {r.cancel_requested_at && (
              <div>
                <dt>Cancellation requested</dt>
                <dd>
                  <Timestamp value={r.cancel_requested_at} />
                </dd>
              </div>
            )}
          </dl>
        </section>
        <div
          className="extraction-table-scroll"
          role="region"
          aria-label="Execution steps, scrollable"
          tabIndex={0}
        >
          <table className="extraction-table">
            <caption>Execution steps in order</caption>
            <thead>
              <tr>
                <th scope="col">Step</th>
                <th scope="col" className="extraction-num">
                  Attempt
                </th>
                <th scope="col">Status</th>
                <th scope="col">Started</th>
                <th scope="col">Finished</th>
              </tr>
            </thead>
            <tbody>
              {steps.data.items.map((s) => (
                <tr key={s.id}>
                  <td className="extraction-mono">{s.step_name}</td>
                  <td className="extraction-num">{s.attempt}</td>
                  <td>
                    <StatusBadge
                      status={s.status}
                      label={s.error ? `${humanize(s.status)}: ${s.error.error.code}` : undefined}
                    />
                  </td>
                  <td className="extraction-nowrap">
                    {s.started_at ? <Timestamp value={s.started_at} /> : "Not started"}
                  </td>
                  <td className="extraction-nowrap">
                    {s.finished_at ? <Timestamp value={s.finished_at} /> : "Not finished"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ExtractionPagination
          path={`/extraction-runs/${r.id}`}
          query={Object.fromEntries(query)}
          page={steps.data}
        />
        <RunEvents key={r.id} runId={r.id} />
        <ActionForm
          key={`cancel:${r.id}`}
          action="cancel"
          path={`runs/${r.id}`}
          initialEtag={run.etag}
          permitted={
            permissions.data.allowed_actions.includes("cancel") &&
            ["queued", "running", "waiting_review"].includes(r.status)
          }
        />
        <ActionForm
          key={`rerun:${r.id}`}
          action="rerun"
          path={`runs/${r.id}/rerun`}
          permitted={permissions.data.allowed_actions.includes("rerun")}
        />
      </ExtractionShell>
    );
  } catch {
    return (
      <ExtractionShell title="Extraction run">
        <ExtractionError />
      </ExtractionShell>
    );
  }
}
