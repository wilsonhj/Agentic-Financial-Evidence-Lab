import { describe, expect, it } from "vitest";

import { candidateLabel, formatUtc, humanizeCode, shortId, splitTimings } from "./labels";

describe("Observatory display labels", () => {
  it("maps known codes and humanizes unknown ones", () => {
    expect(humanizeCode("fact_lookup")).toBe("Fact lookup");
    expect(humanizeCode("temporal_after_cutoff")).toBe("Published after cutoff");
    expect(humanizeCode("dedupe_near_duplicate")).toBe("Near-duplicate");
    expect(humanizeCode("partially_supported")).toBe("Partially supported");
    expect(humanizeCode("run_started")).toBe("Run started");
    expect(humanizeCode("succeeded")).toBe("Succeeded");
  });

  it("shortens ids to their leading eight characters", () => {
    expect(shortId("ffffffff-0000-4000-8000-000000000001")).toBe("ffffffff");
  });

  it("formats UTC timestamps compactly, keeping non-zero seconds and milliseconds", () => {
    expect(formatUtc("2026-07-01T12:00:00Z")).toBe("2026-07-01 12:00 UTC");
    expect(formatUtc("2026-06-30T23:59:59Z")).toBe("2026-06-30 23:59:59 UTC");
    expect(formatUtc("2026-07-01T12:00:00.100Z")).toBe("2026-07-01 12:00:00.100 UTC");
    expect(formatUtc("not a date")).toBe("not a date");
  });

  it("names candidates by fused rank, falling back to the short id", () => {
    const id = "10101010-0000-4000-8000-000000000004";
    expect(candidateLabel({ item_id: id, kind: "passage", fused_rank: 4 })).toBe(
      "Passage, fused rank 4",
    );
    expect(candidateLabel({ item_id: id, kind: "table_row", fused_rank: null })).toBe(
      "Table row 10101010",
    );
  });

  it("keeps a recorded total out of the stages and uses it as the elapsed time", () => {
    // API-produced traces carry an aggregate `total` next to the stage entries.
    expect(splitTimings({ planning: 5, retrieving: 40, total: 90 })).toEqual({
      stages: [
        ["planning", 5],
        ["retrieving", 40],
      ],
      totalMs: 90,
    });
  });

  it("sums the stages when no total is recorded", () => {
    expect(splitTimings({ plan: 22, retrieve: 61 })).toEqual({
      stages: [
        ["plan", 22],
        ["retrieve", 61],
      ],
      totalMs: 83,
    });
    expect(splitTimings({})).toEqual({ stages: [], totalMs: 0 });
  });
});
