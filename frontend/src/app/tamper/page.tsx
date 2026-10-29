import type { Metadata } from "next";

import { TamperPage } from "@/features/tamper/TamperPage";

export const metadata: Metadata = { title: "Tamper ladder · Tallyproof" };

export default function Tamper() {
  return <TamperPage />;
}
