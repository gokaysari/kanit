// Paylaşım (Open Graph) görseli. Derleme sırasında her dil için bir kez PNG olarak üretilir;
// metinler sözlükten, ad site.config.ts'den gelir, yani ad değişince görsel de değişir.
import { readFile } from "node:fs/promises";
import { join } from "node:path";

import { ImageResponse } from "next/og";

import { NARROW_LINE } from "@/content/record";
import type { Dictionary } from "@/content/types";
import { site } from "@/site.config";

export const ogSize = { width: 1200, height: 630 };

// globals.css ile aynı renk belirteçleri (görsel CSS değişkeni okuyamaz).
const color = {
  ink: "#152238",
  inkSoft: "#4a5a73",
  paper: "#f3f5f8",
  sheet: "#ffffff",
  rule: "#c9d2de",
  ok: "#1f7a50",
  okWash: "#e4f3ea",
};

// Görsel oluşturucu woff2 okuyamaz; @fontsource paketindeki woff dosyaları kullanılır.
// latin-ext, Türkçe karakterler (ş, ğ, İ) içindir. Oluşturucu aynı adlı yazı tiplerinden
// yalnızca birini kullandığı için latin-ext ayrı adla kaydedilir ve aile listesinde ikinci sıradadır.
const CONDENSED = "Cond, CondExt";
const SANS = "Sans, SansExt";
const MONO = "Mono, MonoExt";

async function font(pkg: string, file: string) {
  return readFile(join(process.cwd(), "node_modules/@fontsource", pkg, "files", file));
}

async function fonts() {
  const [condLatin, condExt, sansLatin, sansExt, monoLatin, monoExt] = await Promise.all([
    font("ibm-plex-sans-condensed", "ibm-plex-sans-condensed-latin-700-normal.woff"),
    font("ibm-plex-sans-condensed", "ibm-plex-sans-condensed-latin-ext-700-normal.woff"),
    font("ibm-plex-sans", "ibm-plex-sans-latin-500-normal.woff"),
    font("ibm-plex-sans", "ibm-plex-sans-latin-ext-500-normal.woff"),
    font("ibm-plex-mono", "ibm-plex-mono-latin-400-normal.woff"),
    font("ibm-plex-mono", "ibm-plex-mono-latin-ext-400-normal.woff"),
  ]);
  return [
    { name: "Cond", data: condLatin, weight: 700 as const },
    { name: "CondExt", data: condExt, weight: 700 as const },
    { name: "Sans", data: sansLatin, weight: 500 as const },
    { name: "SansExt", data: sansExt, weight: 500 as const },
    { name: "Mono", data: monoLatin, weight: 400 as const },
    { name: "MonoExt", data: monoExt, weight: 400 as const },
  ];
}

export async function renderOgImage(dict: Dictionary) {
  // Tur 2: sitedeki örnek kayıtta Batfish'in kabul ettiği gerçek öneri.
  const accepted = dict.record.rounds[1];

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "64px 72px",
          background: color.paper,
          color: color.ink,
          fontFamily: SANS,
        }}
      >
        <div style={{ display: "flex", fontFamily: CONDENSED, fontSize: 44, fontWeight: 700 }}>
          {site.name}
          <span style={{ color: color.ok }}>.</span>
        </div>

        <div
          style={{
            display: "flex",
            fontFamily: CONDENSED,
            fontSize: 78,
            fontWeight: 700,
            lineHeight: 1.02,
            letterSpacing: "-0.02em",
            maxWidth: 1000,
          }}
        >
          {dict.hero.title}
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 24,
            padding: "22px 26px",
            background: color.sheet,
            border: `2px solid ${color.rule}`,
            borderRadius: 8,
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", fontSize: 22, color: color.inkSoft }}>{dict.og.label}</div>
            <div
              style={{
                display: "flex",
                fontFamily: MONO,
                fontSize: 22,
                padding: "6px 10px",
                background: color.okWash,
                color: color.ok,
              }}
            >
              {NARROW_LINE}
            </div>
          </div>
          <div
            style={{
              display: "flex",
              flexShrink: 0,
              fontFamily: CONDENSED,
              fontSize: 34,
              fontWeight: 700,
              letterSpacing: "0.04em",
              color: color.ok,
              padding: "8px 16px",
              border: `4px solid ${color.ok}`,
              borderRadius: 6,
              transform: "rotate(-2deg)",
            }}
          >
            {accepted.stamp}
          </div>
        </div>
      </div>
    ),
    { ...ogSize, fonts: await fonts() },
  );
}
