"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import {
  persistTheme,
  resolveTheme,
  THEME_ATTRIBUTE,
  THEMES,
  writeStoredTheme,
  type Theme,
} from "./theme";

const themeLabels: Record<Theme, string> = {
  system: "System",
  light: "Light",
  oled: "OLED Black",
};

function subscribe(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributeFilter: [THEME_ATTRIBUTE] });
  return () => observer.disconnect();
}

const readTheme = (): Theme => resolveTheme(document.documentElement.getAttribute(THEME_ATTRIBUTE));
const serverTheme = (): Theme => "system";

export function ThemeSwitcher() {
  const theme = useSyncExternalStore(subscribe, readTheme, serverTheme);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Mirror the cookie-selected theme into localStorage (best effort only).
  useEffect(() => {
    writeStoredTheme(theme);
  }, [theme]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="theme-switcher" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        data-testid="button-theme-menu"
        className="icon-button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-label="Choose appearance"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M20 15.4A8.5 8.5 0 0 1 8.6 4 8.5 8.5 0 1 0 20 15.4Z" />
        </svg>
      </button>
      {open && (
        <div className="theme-popover" data-testid="theme-popover">
          <b>Appearance</b>
          {THEMES.map((value) => (
            <button
              type="button"
              data-testid={`button-theme-${value}`}
              key={value}
              onClick={() => {
                persistTheme(value);
                setOpen(false);
              }}
              aria-pressed={theme === value}
            >
              {themeLabels[value]}
              {theme === value && <span>Active</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
