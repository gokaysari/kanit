import type { MetadataRoute } from "next";

import { site } from "@/site.config";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${site.url}/`, alternates: { languages: { tr: `${site.url}/`, en: `${site.url}/en/` } } },
    { url: `${site.url}/en/`, alternates: { languages: { tr: `${site.url}/`, en: `${site.url}/en/` } } },
  ];
}
