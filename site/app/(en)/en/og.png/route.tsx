// Statik çıktıda out/en/og.png olarak yazılır; uzantılı dosya statik sunucularda image/png döner.
import { renderOgImage } from "@/app/og";
import { en } from "@/content/en";

export const dynamic = "force-static";

export function GET() {
  return renderOgImage(en);
}
