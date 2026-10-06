import type { ReactNode } from "react";

import "../styles";
import { buildMetadata } from "../metadata";
import { en } from "@/content/en";

export const metadata = buildMetadata(en);

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
