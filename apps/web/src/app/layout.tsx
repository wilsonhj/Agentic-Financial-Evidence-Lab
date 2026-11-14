import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";

import { SiteNav } from "../components/SiteNav";
import { ThemeSwitcher } from "../components/ThemeSwitcher";
import { themeBootScript } from "../components/theme";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Financial Evidence Lab",
    template: "%s — Financial Evidence Lab",
  },
  description:
    "Filings, extraction review, earnings updates, and search runs, each figure linked to its source evidence.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // The boot script replaces the server default with the saved theme before
    // first paint, so the attribute can legitimately differ at hydration.
    <html lang="en" data-fel-theme="system" data-scroll-behavior="smooth" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootScript }} />
      </head>
      <body>
        <a href="#main-content" className="skip-link">
          Skip to main content
        </a>
        <header className="site-header">
          <h1>
            <Link href="/">Financial Evidence Lab</Link>
          </h1>
          <p className="tagline">Every figure traced to its source evidence</p>
          <SiteNav />
          <ThemeSwitcher />
        </header>
        {children}
      </body>
    </html>
  );
}
