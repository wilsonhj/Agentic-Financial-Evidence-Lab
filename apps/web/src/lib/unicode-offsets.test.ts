import { describe, expect, it } from "vitest";

import { sha256Hex, verifySpanIntegrity } from "./citation-integrity";
import type { SectionRecord, SourceSpanRecord } from "./contracts";
import { codePointLength, extractSpanText, segmentSection } from "./spans";

// The worker's Python parser counts canonical text in Unicode code points.
const section: SectionRecord = {
  id: "section",
  document_version_id: "version",
  order: 1,
  level: 1,
  title: "Test",
  start_char: 400,
  end_char: 403,
  content: "A😀B",
};
const span: SourceSpanRecord = {
  id: "span",
  span: {
    document_version_id: "version",
    section_id: "section",
    start_char: 402,
    end_char: 403,
    text_hash: `sha256:${sha256Hex("B")}`,
  },
};

describe("canonical Unicode offsets", () => {
  it("verifies and quotes a valid span after a supplementary character", () => {
    expect(verifySpanIntegrity([section], [span])).toEqual({ verified: [span], failures: [] });
    expect(extractSpanText(section, span)).toBe("B");
  });

  it("highlights the exact span after a supplementary character", () => {
    const segments = segmentSection(section, [span]);
    expect(
      segments.filter((segment) => segment.spanIds.includes("span")).map((segment) => segment.text),
    ).toEqual(["B"]);
    expect(segments.map((segment) => segment.text).join("")).toBe(section.content);
  });

  it("verifies and highlights a span containing a supplementary character", () => {
    const containing: SourceSpanRecord = {
      ...span,
      span: { ...span.span, start_char: 401, text_hash: `sha256:${sha256Hex("😀B")}` },
    };
    expect(verifySpanIntegrity([section], [containing]).verified).toEqual([containing]);
    expect(extractSpanText(section, containing)).toBe("😀B");
    expect(segmentSection(section, [containing]).map((segment) => segment.text)).toEqual([
      "A",
      "😀B",
    ]);
  });

  it("still rejects a hash mismatch for Unicode text", () => {
    const corrupt: SourceSpanRecord = {
      ...span,
      span: { ...span.span, text_hash: `sha256:${sha256Hex("A")}` },
    };
    expect(verifySpanIntegrity([section], [corrupt])).toEqual({
      verified: [],
      failures: [{ spanId: "span", sectionId: "section", reason: "text_hash_mismatch" }],
    });
  });

  it("segments overlapping spans on code-point boundaries", () => {
    const containing: SourceSpanRecord = {
      ...span,
      id: "containing",
      span: { ...span.span, start_char: 401, text_hash: `sha256:${sha256Hex("😀B")}` },
    };
    expect(verifySpanIntegrity([section], [span, containing]).verified).toEqual([span, containing]);
    expect(
      segmentSection(section, [span, containing]).map(({ text, spanIds }) => ({ text, spanIds })),
    ).toEqual([
      { text: "A", spanIds: [] },
      { text: "😀", spanIds: ["containing"] },
      { text: "B", spanIds: ["containing", "span"] },
    ]);
  });

  it("preserves decomposed combining marks without normalization", () => {
    const decomposed: SectionRecord = { ...section, content: "😀e\u0301B", end_char: 404 };
    const accented: SourceSpanRecord = {
      ...span,
      span: {
        ...span.span,
        start_char: 401,
        end_char: 403,
        text_hash: `sha256:${sha256Hex("e\u0301")}`,
      },
    };
    expect(verifySpanIntegrity([decomposed], [accented]).verified).toEqual([accented]);
    expect(extractSpanText(decomposed, accented)).toBe("e\u0301");
    expect(segmentSection(decomposed, [accented]).map((segment) => segment.text)).toEqual([
      "😀",
      "e\u0301",
      "B",
    ]);
  });

  it("maps boundaries around multiple supplementary characters", () => {
    const multiple: SectionRecord = { ...section, content: "A😀B🚀C", end_char: 405 };
    const rocket: SourceSpanRecord = {
      ...span,
      span: {
        ...span.span,
        start_char: 403,
        end_char: 404,
        text_hash: `sha256:${sha256Hex("🚀")}`,
      },
    };
    const tail: SourceSpanRecord = {
      ...span,
      id: "tail",
      span: { ...span.span, start_char: 404, end_char: 405, text_hash: `sha256:${sha256Hex("C")}` },
    };
    expect(verifySpanIntegrity([multiple], [rocket, tail]).verified).toEqual([rocket, tail]);
    expect(segmentSection(multiple, [rocket, tail]).map((segment) => segment.text)).toEqual([
      "A😀B",
      "🚀",
      "C",
    ]);
  });

  it("still rejects malformed ranges and preserves the full unhighlighted text", () => {
    const outside: SourceSpanRecord = {
      ...span,
      span: { ...span.span, end_char: 404 },
    };
    expect(verifySpanIntegrity([section], [outside]).failures[0]?.reason).toBe(
      "offsets_out_of_range",
    );
    const segments = segmentSection(section, [outside]);
    expect(segments.map((segment) => segment.text).join("")).toBe(section.content);
    expect(segments.every((segment) => segment.spanIds.length === 0)).toBe(true);
  });

  it("counts code points as canonical offsets do (Python len)", () => {
    expect(codePointLength("")).toBe(0);
    expect(codePointLength("abc")).toBe(3);
    expect(codePointLength("A😀B")).toBe(3);
    expect(codePointLength("🇺🇸")).toBe(2);
    expect(codePointLength("e\u0301")).toBe(2);
    expect(codePointLength("\uD800x")).toBe(2);
  });
});
