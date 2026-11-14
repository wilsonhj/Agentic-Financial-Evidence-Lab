import type { Metadata } from "next";

import DeskClient from "./DeskClient";

export const metadata: Metadata = {
  title: "Earnings Update Desk",
  description: "Evidence-linked earnings review, extraction approval, and model impact preview.",
};

// The appearance is site-wide: the root layout's boot script sets
// `data-fel-theme` on <html> from the `fel-theme` cookie before first paint.
export default function DeskPage() {
  return <DeskClient />;
}
