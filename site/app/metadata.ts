import type { Metadata } from "next";

import type { Dictionary } from "@/content/types";
import { site } from "@/site.config";

export function buildMetadata(dict: Dictionary): Metadata {
  const path = dict.lang === "tr" ? "/" : "/en/";
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
    },
  };
}
