import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import DeskPage from "./page";

describe("DeskPage inside the shared app shell", () => {
  const markup = renderToStaticMarkup(<DeskPage />);

  it("is the skip-link target and leaves the theme to <html>", () => {
    expect(markup).toContain('id="main-content"');
    expect(markup).toContain('data-testid="desk-shell"');
    expect(markup).not.toContain("data-fel-theme");
  });

  it("does not draw its own brand or appearance control", () => {
    expect(markup).not.toContain("desk-brand");
    expect(markup).not.toContain("button-theme-menu");
    expect(markup).not.toContain("Open extraction review");
  });

  it("keeps the Desk section tabs", () => {
    for (const id of ["coverage", "research", "review", "model"]) {
      expect(markup).toContain(`data-testid="nav-section-${id}"`);
    }
  });
});
