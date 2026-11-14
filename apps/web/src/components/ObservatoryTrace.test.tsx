import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { ObservatoryTrace } from "./ObservatoryTrace";
import { MOCK_QUERY_SNAPSHOT, MOCK_TRACE } from "../lib/observatory/fixtures/synthetic-trace";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

// Version -> document map covering the fixture spans used by the mock trace.
const DOC_MAP = {
  "aaaaaaaa-0000-4000-8000-000000001001": "aaaaaaaa-0000-4000-8000-000000000001",
  "aaaaaaaa-0000-4000-8000-000000001002": "aaaaaaaa-0000-4000-8000-000000000002",
};

function render() {
  return renderToStaticMarkup(
    <ObservatoryTrace
      trace={MOCK_TRACE}
      snapshot={MOCK_QUERY_SNAPSHOT}
      documentIdByVersionId={DOC_MAP}
    />,
  );
}

describe("ObservatoryTrace", () => {
  it("renders the plan, variants, filters and the four retrieval lanes", () => {
    const markup = render();
    expect(markup).toContain("Query plan");
    expect(markup).toContain("fact_lookup");
    expect(markup).toContain(MOCK_QUERY_SNAPSHOT.question);
    expect(markup).toContain("Q1 2026 total revenue"); // variant
    expect(markup).toContain("10-Q"); // filter form
    for (const lane of ["Dense", "Lexical", "Facts", "Tables"]) {
      expect(markup).toContain(lane);
    }
  });

  it("renders raw, normalized, RRF and rerank ranks for candidates", () => {
    const markup = render();
    expect(markup).toContain("0.8123"); // raw score
    expect(markup).toContain("0.0164"); // rrf contribution
    expect(markup).toContain("0.9910"); // rerank score is present via candidate data
  });

  it("links a supported candidate to its exact reader span", () => {
    const markup = render();
    expect(markup).toContain(
      "/reader/aaaaaaaa-0000-4000-8000-000000000001?span=cccccccc-0000-4000-8000-000000000001",
    );
  });

  it("never renders future or cross-version evidence as supported", () => {
    const markup = render();
    // Both appear only as rejected, with their reason codes.
    expect(markup).toContain("temporal_after_cutoff");
    expect(markup).toContain("cross_version");
    // The rejected-candidates list is present.
    expect(markup).toContain("Rejected candidates");
  });

  it("renders claims with citation status and shows the contradiction distinctly", () => {
    const markup = render();
    expect(markup).toContain("Claims and citations");
    expect(markup).toContain("supported");
    expect(markup).toContain("contradicted");
    expect(markup).toContain("entailed");
  });

  it("renders budgets, latency and cost", () => {
    const markup = render();
    expect(markup).toContain("Budgets, latency and cost");
    expect(markup).toContain("0.0421"); // cost usd
    // Per-stage latency is shown once, as a captioned table with human stage names.
    expect(markup).toContain("Stage latency");
    expect(markup).toContain('title="generate">Generate');
    expect(markup).toContain(">812<");
    expect(markup.match(/>812</g)).toHaveLength(1);
  });

  it("does not count a recorded total as a stage or double the elapsed time", () => {
    const markup = renderToStaticMarkup(
      <ObservatoryTrace
        trace={{ ...MOCK_TRACE, timings_ms: { planning: 10, retrieving: 30, total: 40 } }}
        snapshot={MOCK_QUERY_SNAPSHOT}
        documentIdByVersionId={DOC_MAP}
      />,
    );
    // The aggregate is the footer total, not a stage row, and not 80 ms.
    expect(markup).not.toContain('title="total"');
    expect(markup).toContain("<strong>Total latency:</strong> 40 ms.");
    expect(markup).not.toContain(">80<");
    // Shares are of the elapsed 40 ms: 25% and 75%.
    expect(markup).toContain(">25%<");
    expect(markup).toContain(">75%<");
  });

  it("still shows the elapsed time when only an aggregate total was recorded", () => {
    const markup = renderToStaticMarkup(
      <ObservatoryTrace
        trace={{ ...MOCK_TRACE, timings_ms: { total: 57 } }}
        snapshot={MOCK_QUERY_SNAPSHOT}
        documentIdByVersionId={DOC_MAP}
      />,
    );
    expect(markup).not.toContain("<caption>Stage latency</caption>");
    expect(markup).toContain(
      "<strong>Total latency:</strong> 57 ms. No per-stage timings were recorded.",
    );
    expect(markup).toContain("<strong>Total latency:</strong> 57 ms.");
  });

  it("orders the page for a reader: question and status, then claims, then the pipeline", () => {
    const markup = render();
    const order = ["obs-plan", "obs-claims", "obs-flow", "obs-lanes", "obs-timeline", "obs-budget"];
    const positions = order.map((id) => markup.indexOf(`id="${id}"`));
    expect(positions.every((position) => position >= 0)).toBe(true);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });

  it("shows human labels and keeps the raw codes and full ids available", () => {
    const markup = render();
    expect(markup).toContain('title="fact_lookup">Fact lookup');
    expect(markup).toContain('title="partially_supported">Partially supported');
    expect(markup).toContain("Published after cutoff");
    expect(markup).toContain("Near-duplicate");
    // Run ids are shortened with the full id in the tooltip...
    expect(markup).toContain(`title="${MOCK_TRACE.run_id}">ffffffff`);
    // ...but the version pins needed to reproduce the run are shown in full.
    expect(markup).toContain(
      `<code class="obs-id obs-id-full">${MOCK_TRACE.plan.corpus_version_id}</code>`,
    );
    expect(markup).toContain(
      `<code class="obs-id obs-id-full">${MOCK_TRACE.plan.index_version_id}</code>`,
    );
    // Rejected candidates are told apart by fused rank, not a shared id prefix.
    expect(markup).toContain("Passage, fused rank 4");
  });

  it("scrolls each lane table inside its own labelled region", () => {
    const markup = render();
    expect(markup).toContain('role="region" aria-labelledby="obs-lane-dense-heading"');
  });
});
