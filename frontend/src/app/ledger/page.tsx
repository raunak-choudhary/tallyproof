import type { Metadata } from "next";

import { LedgerPage } from "@/features/ledger/LedgerPage";

export const metadata: Metadata = { title: "The ledger · Tallyproof" };

// Live when a WebSocket server is configured, otherwise a replay of the signed bundle.
export default function Ledger() {
  return <LedgerPage />;
}
