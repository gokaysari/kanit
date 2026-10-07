import type { ReactNode } from "react";

import "../globals.css";
import { buildMetadata } from "../metadata";
import { tr } from "@/content/tr";

export const metadata = buildMetadata(tr);

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}
