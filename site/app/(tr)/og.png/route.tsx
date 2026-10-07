// Paylaşım görseli; Workers üzerinde istek anında üretilir (yazı tipleri pakete gömülü, bkz. app/og.tsx).
import { renderOgImage } from "@/app/og";
import { tr } from "@/content/tr";

export const dynamic = "force-static";

export function GET() {
  return renderOgImage(tr);
}
