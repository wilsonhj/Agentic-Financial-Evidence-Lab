import { afterEach, describe, expect, it } from "vitest";

import { persistTheme, THEME_ATTRIBUTE } from "./theme";

describe("persistTheme", () => {
  const originalDocument = globalThis.document;
  const originalWindow = globalThis.window;

  afterEach(() => {
    Object.defineProperty(globalThis, "document", {
      value: originalDocument,
      configurable: true,
      writable: true,
    });
    Object.defineProperty(globalThis, "window", {
      value: originalWindow,
      configurable: true,
      writable: true,
    });
  });

  function installDom(protocol: string): {
    attrs: Record<string, string>;
    getCookie: () => string;
  } {
    const attrs: Record<string, string> = {};
    let cookie = "";
    Object.defineProperty(globalThis, "document", {
      value: {
        documentElement: {
          setAttribute: (name: string, value: string) => {
            attrs[name] = value;
          },
        },
        get cookie() {
          return cookie;
        },
        set cookie(value: string) {
          cookie = value;
        },
      },
      configurable: true,
      writable: true,
    });
    Object.defineProperty(globalThis, "window", {
      value: { location: { protocol } },
      configurable: true,
      writable: true,
    });
    return { attrs, getCookie: () => cookie };
  }

  it("sets the Secure attribute when served over HTTPS", () => {
    const dom = installDom("https:");
    persistTheme("oled");
    expect(dom.attrs[THEME_ATTRIBUTE]).toBe("oled");
    expect(dom.getCookie()).toBe("fel-theme=oled; Path=/; Max-Age=31536000; SameSite=Lax; Secure");
  });

  it("omits the Secure attribute on plain HTTP local development", () => {
    const dom = installDom("http:");
    persistTheme("light");
    expect(dom.attrs[THEME_ATTRIBUTE]).toBe("light");
    expect(dom.getCookie()).toBe("fel-theme=light; Path=/; Max-Age=31536000; SameSite=Lax");
  });
});
