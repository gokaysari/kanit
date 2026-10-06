import type { Metadata } from "next";

import type { Dictionary } from "@/content/types";
import { site } from "@/site.config";

import { ogSize } from "./og";

export function buildMetadata(dict: Dictionary): Metadata {
  const path = dict.lang === "tr" ? "/" : "/en/";
  // Paylaşım görseli: app/(tr)/og.png ve app/(en)/en/og.png rotalarında derlemede üretilir.
  const image = { url: `${path}og.png`, ...ogSize, alt: dict.og.alt, type: "image/png" };
  return {
    metadataBase: new URL(site.url),
    title: dict.meta.title,
    description: dict.meta.description,
    alternates: { canonical: path, languages: { tr: "/", en: "/en/" } },
    openGraph: {
      title: dict.meta.title,
      description: dict.meta.description,
      url: path,
      siteName: site.name,
      locale: dict.lang === "tr" ? "tr_TR" : "en_US",
      type: "website",
      images: [image],
    },
    twitter: { card: "summary_large_image", images: [image] },
  };
}
