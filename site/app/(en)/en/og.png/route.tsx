// Paylaşım görseli; Workers üzerinde istek anında üretilir (yazı tipleri pakete gömülü, bkz. app/og.tsx).
import { renderOgImage } from "@/app/og";
import { en } from "@/content/en";

export const dynamic = "force-static";

export function GET() {
  return renderOgImage(en);
}
