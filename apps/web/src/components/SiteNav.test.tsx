import { describe, expect, it } from "vitest";

import { isCurrentSection, navItems } from "./SiteNav";

const currentFor = (pathname: string | null) =>
  navItems.filter((item) => isCurrentSection(item, pathname)).map((item) => item.label);

describe("primary navigation current section", () => {
  it.each([
    ["/", ["Filings"]],
    ["/reader/aaaaaaaa-0000-4000-8000-000000000001", ["Filings"]],
    ["/desk", ["Update Desk"]],
    ["/extractions", ["Extractions"]],
    ["/extractions/abc", ["Extractions"]],
    ["/extraction-runs/run-1/events", ["Extractions"]],
    ["/approved-extractions/rec-1/versions", ["Extractions"]],
    ["/observatory/runs/run-1", ["Observatory"]],
    ["/desktop", []],
    [null, []],
  ])("marks %s as %j", (pathname, expected) => {
    expect(currentFor(pathname)).toEqual(expected);
  });
});
