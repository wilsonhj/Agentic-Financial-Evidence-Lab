import Link from "next/link";

import "../styles/filings.css";

/** Links always target a known application route; cursors remain opaque query values. */
export function PageNavigation({
  path,
  params = {},
  nextCursor,
  previousCursor,
  order = "asc",
  cursorKey = "cursor",
  orderKey = "order",
  label = "Pages",
}: {
  path: string;
  params?: Record<string, string>;
  nextCursor: string | null;
  previousCursor: string | null;
  order?: "asc" | "desc";
  cursorKey?: string;
  orderKey?: string;
  label?: string;
}) {
  const href = (direction: "asc" | "desc", cursor?: string) => {
    const query = new URLSearchParams(params);
    query.delete(cursorKey);
    query.set(orderKey, direction);
    if (cursor) query.set(cursorKey, cursor);
    return `${path}?${query}`;
  };
  const sortLink = (direction: "asc" | "desc", text: string) => (
    <Link
      className="page-nav-link"
      href={href(direction)}
      aria-current={order === direction ? "true" : undefined}
    >
      {text}
    </Link>
  );
  const pageLink = (cursor: string | null, text: string) =>
    cursor ? (
      <Link className="page-nav-link" href={href(order, cursor)}>
        {text}
      </Link>
    ) : (
      <span className="page-nav-link" aria-disabled="true">
        {text}
      </span>
    );
  return (
    <nav className="obs-actions page-nav" aria-label={label}>
      <span className="page-nav-group">
        {sortLink("asc", "Oldest first")}
        {sortLink("desc", "Newest first")}
      </span>
      <span className="page-nav-group">
        {pageLink(previousCursor, "Previous page")}
        {pageLink(nextCursor, "Next page")}
      </span>
    </nav>
  );
}
