import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import RootLayout from "./layout";

const renderLayout = () => renderToStaticMarkup(RootLayout({ children: <p>page content</p> }));

describe("RootLayout skip link", () => {
  it("renders a 'Skip to main content' link as the first focusable element in the body", async () => {
    const markup = await renderLayout();
    const skipLinkIndex = markup.indexOf('class="skip-link"');
    const headerIndex = markup.indexOf('class="site-header"');
    expect(skipLinkIndex).toBeGreaterThan(-1);
    expect(headerIndex).toBeGreaterThan(-1);
    // The skip link precedes the repeated header/nav chrome it exists to
    // let a keyboard user bypass.
    expect(skipLinkIndex).toBeLessThan(headerIndex);
  });

  it("targets the main-content landmark", async () => {
    const markup = await renderLayout();
    expect(markup).toContain('href="#main-content"');
    expect(markup).toContain("Skip to main content");
  });

  it("is visually hidden until focused (not permanently visible chrome)", async () => {
    const markup = await renderLayout();
    // Hidden by default via the shared .skip-link rule, revealed on :focus —
    // asserted at the CSS layer below, not by inspecting inline styles here.
    expect(markup).toContain('class="skip-link"');
  });
});

describe("RootLayout skip-link stylesheet contract", async () => {
  const { readFileSync } = await import("node:fs");
  const css = readFileSync(new URL("./globals.css", import.meta.url), "utf8");

  it("hides the skip link by default and restores it on focus", () => {
    expect(css).toMatch(/\.skip-link\s*\{[^}]*clip:\s*rect\(0,\s*0,\s*0,\s*0\)/);
    expect(css).toMatch(/\.skip-link:focus\s*\{[^}]*clip:\s*auto/);
  });
});

describe("RootLayout site-wide theme", () => {
  it("puts the theme on <html> with a system default for every route", () => {
    expect(renderLayout()).toMatch(/<html[^>]*data-fel-theme="system"/);
  });

  it("applies the saved cookie theme in <head> before the body paints", () => {
    const markup = renderLayout();
    const scriptIndex = markup.indexOf("<script>");
    expect(scriptIndex).toBeGreaterThan(-1);
    expect(scriptIndex).toBeLessThan(markup.indexOf("<body"));
    expect(markup).toContain("fel-theme=");
  });

  it("puts the appearance control in the shared header", () => {
    const markup = renderLayout();
    const header = markup.slice(markup.indexOf('class="site-header"'), markup.indexOf("</header>"));
    expect(header).toContain('data-testid="button-theme-menu"');
  });
});

describe("theme boot script", () => {
  const run = async (cookie: string) => {
    const { themeBootScript } = await import("../components/theme");
    const attributes: Record<string, string> = {};
    const document = {
      cookie,
      documentElement: {
        setAttribute: (name: string, value: string) => {
          attributes[name] = value;
        },
      },
    };
    new Function("document", themeBootScript)(document);
    return attributes["data-fel-theme"];
  };

  it.each([
    ["fel-theme=oled", "oled"],
    ["a=1; fel-theme=light; b=2", "light"],
    ["fel-theme=system", "system"],
    ["fel-theme=chartreuse", "system"],
    ["", "system"],
  ])("maps cookie %j to %s", async (cookie, expected) => {
    expect(await run(cookie)).toBe(expected);
  });
});

describe("RootLayout primary navigation", () => {
  it("links every workspace, including extraction review", () => {
    const links = renderLayout().match(/<a [^>]*>/g) ?? [];
    for (const [testId, href] of [
      ["link-update-desk", "/desk"],
      ["link-filings", "/"],
      ["link-extractions", "/extractions"],
      ["link-observatory", "/observatory"],
    ]) {
      const link = links.find((tag) => tag.includes(`data-testid="${testId}"`));
      expect(link).toContain(`href="${href}"`);
    }
  });
});
