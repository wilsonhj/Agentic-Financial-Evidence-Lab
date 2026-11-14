"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = {
  href: string;
  label: string;
  testId: string;
  /** Path prefixes (besides `href`) that belong to this workspace. */
  matches: readonly string[];
};

export const navItems: readonly NavItem[] = [
  { href: "/desk", label: "Update Desk", testId: "link-update-desk", matches: ["/desk"] },
  { href: "/", label: "Filings", testId: "link-filings", matches: ["/reader"] },
  {
    href: "/extractions",
    label: "Extractions",
    testId: "link-extractions",
    matches: ["/extractions", "/extraction-runs", "/approved-extractions"],
  },
  {
    href: "/observatory",
    label: "Observatory",
    testId: "link-observatory",
    matches: ["/observatory"],
  },
];

const underPrefix = (pathname: string, prefix: string) =>
  pathname === prefix || pathname.startsWith(`${prefix}/`);

export function isCurrentSection(item: NavItem, pathname: string | null): boolean {
  if (pathname === null) return false;
  if (pathname === item.href) return true;
  return item.matches.some((prefix) => underPrefix(pathname, prefix));
}

export function SiteNav() {
  const pathname = usePathname();
  return (
    <nav className="site-nav" aria-label="Primary navigation">
      {navItems.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          data-testid={item.testId}
          aria-current={isCurrentSection(item, pathname) ? "page" : undefined}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
