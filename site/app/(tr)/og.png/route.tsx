// Statik çıktıda out/og.png olarak yazılır; uzantılı dosya statik sunucularda image/png döner.
import { renderOgImage } from "@/app/og";
import { tr } from "@/content/tr";

export const dynamic = "force-static";

export function GET() {
  return renderOgImage(tr);
}
