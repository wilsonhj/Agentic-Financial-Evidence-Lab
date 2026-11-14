import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";

import type { DocumentMeta } from "../lib/contracts";
import { fixtureEvidenceSource } from "../lib/data";
import { loadReaderData, type ReaderData } from "../lib/reader-loader";
import { extractSpanText } from "../lib/spans";
import { DOC_10Q_ID, DOC_10QA_ID } from "../lib/fixtures/synthetic-filing";
import { EvidenceReader } from "./EvidenceReader";

// next/link needs a Next.js runtime context; render it as a plain anchor.
vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

async function readyData(documentId: string): Promise<ReaderData> {
  const result = await loadReaderData(fixtureEvidenceSource, documentId, { siblingLimit: 10 });
  if (result.kind !== "ready") throw new Error(`expected ready, got ${result.kind}`);
  return result.data;
}

function renderReader(documentId: string, data: ReaderData): string {
  return renderToStaticMarkup(
    <EvidenceReader
      documentId={documentId}
      documents={data.documents}
      sections={data.sections}
      spans={data.spans}
      facts={data.facts}
      documentIdBySectionId={data.documentIdBySectionId}
      documentIdBySpanId={data.documentIdBySpanId}
      integrityFailures={data.integrityFailures}
    />,
  );
}

describe("EvidenceReader rendering", () => {
  // Regression (finding 1, ID conflation): with distinct document/version ids
  // the old reader filtered sections and facts by
  // `document_version_id === DocumentMeta.id` and rendered an empty shell —
  // no sections, no span highlights, no facts.
  it("renders sections, span highlights, and facts when document and version ids are distinct", async () => {
    const markup = renderReader(DOC_10Q_ID, await readyData(DOC_10Q_ID));
    // Sections of the viewed filing render.
    expect(markup).toContain("Condensed Consolidated Statements of Operations");
    expect(markup).toContain("Item 2. Management&#x27;s Discussion and Analysis");
    // Span highlights render as citation buttons.
    expect(markup).toContain("span-mark");
    expect(markup).toContain("Cited source span:");
    // Facts of the viewed filing render in the panel (6 facts cite 10-Q spans).
    expect(markup).toContain("Extracted facts");
    expect(markup).toContain("(6 in this filing)");
    expect(markup).toContain("Diluted EPS");
    // The superseded banner links to the amendment.
    expect(markup).toContain("Superseded.");
    expect(markup).toContain(`/reader/${DOC_10QA_ID}`);
  });

  // Regression (finding 5): each document instance derives its own initial
  // state (outline selection) from its own sections; page.tsx keys the
  // component by documentId so navigation remounts with this fresh state.
  it("derives distinct initial reader state per document instance", async () => {
    const markup10q = renderReader(DOC_10Q_ID, await readyData(DOC_10Q_ID));
    const markup10qa = renderReader(DOC_10QA_ID, await readyData(DOC_10QA_ID));
    // Initial active outline entry is the first section of EACH document.
    expect(markup10q).toContain('aria-current="true"');
    expect(markup10qa).toContain('aria-current="true"');
    expect(markup10q).toContain("Part I — Financial Information");
    expect(markup10q).not.toContain("Explanatory Note");
    expect(markup10qa).toContain("Explanatory Note");
    expect(markup10qa).not.toContain("Part I — Financial Information");
  });

  // THE #87 regression case: a valid span in a NON-FIRST section, whose
  // GLOBAL canonical offsets exceed the section-content length, must render
  // its exact hash-verified text as a highlighted citation. Before the
  // coordinate fix this span was dropped as out-of-range (or, worse under the
  // old fixture, section-local offsets silently highlighted the wrong text).
  it("highlights the exact cited text of a non-first-section span with global offsets", async () => {
    const data = await readyData(DOC_10Q_ID);
    const span = data.spans.find((record) => record.id === "cccccccc-0000-4000-8000-000000000001")!;
    const section = data.sections.find((s) => s.id === span.span.section_id)!;
    // Regression precondition (#87): global offset exceeds the section length.
    expect(span.span.start_char).toBeGreaterThan(section.content.length);
    const cited = extractSpanText(section, span);
    expect(cited).toContain("Revenue for the three months ended March 31, 2026");
    const markup = renderReader(DOC_10Q_ID, data);
    expect(markup).toContain(cited!);
    // And nothing was excluded: every fixture span verifies under global
    // coordinates.
    expect(data.integrityFailures).toEqual([]);
  });

  // Regression (issue #87): out-of-section offsets (e.g. section-local
  // leftovers) surface the explicit integrity alert, never a clamped quote.
  it("surfaces the integrity alert for a span outside its section's canonical range", async () => {
    const data = await readyData(DOC_10Q_ID);
    const failedSpan = data.spans.find((span) => data.documentIdBySpanId[span.id] === DOC_10Q_ID)!;
    const tampered: ReaderData = {
      ...data,
      spans: data.spans.filter((span) => span.id !== failedSpan.id),
      integrityFailures: [
        {
          spanId: failedSpan.id,
          sectionId: failedSpan.span.section_id,
          reason: "offsets_out_of_range",
        },
      ],
    };
    const markup = renderReader(DOC_10Q_ID, tampered);
    expect(markup).toContain("Citation integrity error.");
    expect(markup).toContain('role="alert"');
    expect(markup).toContain("outside the section&#x27;s canonical range");
  });

  // Regression (finding 7): absent period fields used to render as
  // "Period undefined to undefined".
  it("renders 'Period n/a' when period fields are absent", async () => {
    const data = await readyData(DOC_10Q_ID);
    const periodless: DocumentMeta[] = data.documents.map((doc) =>
      doc.id === DOC_10Q_ID ? { ...doc, period_start: undefined, period_end: undefined } : doc,
    );
    const markup = renderReader(DOC_10Q_ID, { ...data, documents: periodless });
    expect(markup).toContain("Period n/a");
    expect(markup).not.toContain("undefined");
  });

  // Regression (finding 2): failed citations must surface an explicit,
  // accessible error state in both the reader banner and the fact panel — and
  // the unverified quote must not render.
  it("surfaces a citation integrity error state instead of quoting a failed span", async () => {
    const data = await readyData(DOC_10Q_ID);
    // Fail the statements-revenue span (cited by the first revenue fact).
    const failedSpanId = data.spans.find(
      (span) => data.documentIdBySpanId[span.id] === DOC_10Q_ID,
    )!.id;
    const failedSpan = data.spans.find((span) => span.id === failedSpanId)!;
    const tampered: ReaderData = {
      ...data,
      spans: data.spans.filter((span) => span.id !== failedSpanId),
      integrityFailures: [
        {
          spanId: failedSpanId,
          sectionId: failedSpan.span.section_id,
          reason: "text_hash_mismatch",
        },
      ],
    };
    const markup = renderReader(DOC_10Q_ID, tampered);
    // Reader-level banner (role=alert carries it to assistive tech; the
    // warning glyph and explicit wording make it more than a color change).
    expect(markup).toContain("Citation integrity error.");
    expect(markup).toContain('role="alert"');
    // Fact-panel state names the failed check and withholds the quote.
    expect(markup).toContain("Citation integrity error:");
    expect(markup).toContain("does not match its recorded hash");
  });

  // Observatory candidate deep link: `?span=` pre-selects the exact cited span
  // (aria-pressed) when it belongs to this document, and is ignored otherwise.
  it("pre-selects a deep-linked span belonging to the document", async () => {
    const data = await readyData(DOC_10Q_ID);
    const spanId = "cccccccc-0000-4000-8000-000000000001";
    const markup = renderToStaticMarkup(
      <EvidenceReader
        documentId={DOC_10Q_ID}
        documents={data.documents}
        sections={data.sections}
        spans={data.spans}
        facts={data.facts}
        documentIdBySectionId={data.documentIdBySectionId}
        documentIdBySpanId={data.documentIdBySpanId}
        integrityFailures={data.integrityFailures}
        initialSpanId={spanId}
      />,
    );
    expect(markup).toContain('aria-pressed="true"');
  });

  it("ignores a deep-linked span id that does not belong to the document", async () => {
    const data = await readyData(DOC_10Q_ID);
    const foreignSpanId = "cccccccc-0000-4000-8000-000000000007"; // a 10-Q/A span
    const markup = renderToStaticMarkup(
      <EvidenceReader
        documentId={DOC_10Q_ID}
        documents={data.documents}
        sections={data.sections}
        spans={data.spans}
        facts={data.facts}
        documentIdBySectionId={data.documentIdBySectionId}
        documentIdBySpanId={data.documentIdBySpanId}
        integrityFailures={data.integrityFailures}
        initialSpanId={foreignSpanId}
      />,
    );
    expect(markup).not.toContain('aria-pressed="true"');
  });
});

describe("EvidenceReader conflict summary and history notice", () => {
  it("summarises conflicting duplicate values above the columns with a jump control per passage", async () => {
    const data = await readyData(DOC_10Q_ID);
    // Only the target filing's own facts: the revenue conflict between its
    // Statements of Operations and its MD&A.
    const markup = renderReader(DOC_10Q_ID, {
      ...data,
      facts: data.facts.filter(
        (record) => data.documentIdBySpanId[record.fact.source_span_id] === DOC_10Q_ID,
      ),
    });
    // A labelled region with a heading, not a live alert.
    expect(markup).toContain(
      '<section class="conflict-summary" aria-labelledby="conflict-summary-heading">',
    );
    expect(markup).toMatch(/<h2 id="conflict-summary-heading">.*Conflicting values: Revenue<\/h2>/);
    expect(markup).toContain("1,250,000,000 USD");
    expect(markup).toContain("1,243,000,000 USD");
    expect((markup.match(/<button type="button" class="conflict-jump"/g) ?? []).length).toBe(2);
    // It precedes the three-column layout in DOM (and visual) order.
    expect(markup.indexOf("conflict-summary")).toBeLessThan(markup.indexOf("reader-layout"));
    // The detailed comparison stays in the fact card.
    expect(markup).toContain("Inconsistent duplicate values");
  });

  it("labels a difference explained by an amendment as a restatement, not a conflict", async () => {
    const data = await readyData(DOC_10QA_ID);
    // Net income only: $86.4M in the 10-Q, restated to $79.5M by the 10-Q/A.
    const markup = renderReader(DOC_10QA_ID, {
      ...data,
      facts: data.facts.filter((record) => record.fact.concept === "us-gaap:NetIncomeLoss"),
    });
    expect(markup).toContain(
      '<section class="conflict-summary conflict-summary-restated" aria-labelledby="conflict-summary-heading">',
    );
    expect(markup).toMatch(/<h2 id="conflict-summary-heading">.*Restated by amendment: Net income/);
    expect(markup).not.toContain("Conflicting values");
    expect(markup).toContain("was restated:");
  });

  it("keeps a group that is inconsistent within one filing a conflict even when it was also restated", async () => {
    const data = await readyData(DOC_10QA_ID);
    // Revenue: $1,250.0M vs $1,243.0M inside the 10-Q itself, plus the 10-Q/A value.
    const markup = renderReader(DOC_10QA_ID, {
      ...data,
      facts: data.facts.filter((record) => record.fact.concept.startsWith("us-gaap:Revenue")),
    });
    expect(markup).toContain(
      '<section class="conflict-summary" aria-labelledby="conflict-summary-heading">',
    );
    expect(markup).toMatch(/Conflicting values: Revenue/);
  });

  it("renders no conflict summary when the loaded facts have no inconsistent duplicates", async () => {
    const data = await readyData(DOC_10Q_ID);
    const markup = renderToStaticMarkup(
      <EvidenceReader
        documentId={DOC_10Q_ID}
        documents={data.documents}
        sections={data.sections}
        spans={data.spans}
        facts={data.facts.filter(
          (record) =>
            data.documentIdBySpanId[record.fact.source_span_id] === DOC_10Q_ID &&
            !record.fact.concept.startsWith("us-gaap:Revenue"),
        )}
        documentIdBySectionId={data.documentIdBySectionId}
        documentIdBySpanId={data.documentIdBySpanId}
        integrityFailures={data.integrityFailures}
      />,
    );
    expect(markup).not.toContain("conflict-summary");
  });

  it("puts 'Load related filings' inside the related-history-incomplete notice", async () => {
    const data = await readyData(DOC_10Q_ID);
    const markup = renderToStaticMarkup(
      <EvidenceReader
        documentId={DOC_10Q_ID}
        documents={data.documents}
        sections={data.sections}
        spans={data.spans}
        facts={data.facts}
        documentIdBySectionId={data.documentIdBySectionId}
        documentIdBySpanId={data.documentIdBySpanId}
        integrityFailures={data.integrityFailures}
        historyComplete={false}
        loadRelatedHref="/reader/x?related=1"
      />,
    );
    expect(markup).toMatch(
      /<aside class="reader-banner reader-banner-history" role="status">.*Related history incomplete\..*<a href="\/reader\/x\?related=1">Load related filings<\/a><\/aside>/,
    );
  });
});
