/**
 * Site-wide appearance. The chosen theme lives on `<html data-fel-theme>` so
 * every route reads the same tokens from globals.css. The `fel-theme` cookie
 * is the source of truth; localStorage is a best-effort mirror only.
 */
export type Theme = "system" | "light" | "oled";

export const THEMES: readonly Theme[] = ["system", "light", "oled"];
export const THEME_COOKIE = "fel-theme";
export const THEME_ATTRIBUTE = "data-fel-theme";

export function isValidTheme(value: string | null | undefined): value is Theme {
  return value === "system" || value === "light" || value === "oled";
}

export function resolveTheme(value: string | null | undefined): Theme {
  return isValidTheme(value) ? value : "system";
}

type ThemeStorage = {
  setItem(key: string, value: string): void;
};

function defaultThemeStorage(): ThemeStorage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function writeStoredTheme(
  theme: Theme,
  storage: ThemeStorage | null = defaultThemeStorage(),
): void {
  if (storage === null) return;
  try {
    storage.setItem(THEME_COOKIE, theme);
  } catch {
    // Storage can throw when blocked (private mode, iframe). Cookie + dataset remain.
  }
}

export function persistTheme(theme: Theme): void {
  document.documentElement.setAttribute(THEME_ATTRIBUTE, theme);
  document.cookie = `${THEME_COOKIE}=${theme}; Path=/; Max-Age=31536000; SameSite=Lax`;
  writeStoredTheme(theme);
}

/**
 * Runs in <head> before first paint, so the page never flashes the wrong
 * theme. Reading the cookie here instead of with `cookies()` in the root
 * layout keeps every route's rendering mode (static or dynamic) unchanged.
 */
export const themeBootScript = `(function(){try{var m=/(?:^|;\\s*)fel-theme=([^;]*)/.exec(document.cookie);var t=m&&m[1];if(t!=="light"&&t!=="oled")t="system";document.documentElement.setAttribute("${THEME_ATTRIBUTE}",t);}catch(e){}})();`;
