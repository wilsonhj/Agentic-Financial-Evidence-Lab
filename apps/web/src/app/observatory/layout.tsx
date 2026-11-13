import type { ReactNode } from "react";

import "../../styles/observatory.css";

/** Pass-through layout that scopes the Observatory stylesheet to its routes. */
export default function ObservatoryLayout({ children }: { children: ReactNode }) {
  return children;
}
