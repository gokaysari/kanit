import type { NextConfig } from "next";

const config: NextConfig = {
  trailingSlash: true,
  images: { unoptimized: true },
  // İki ayrı kök düzen (tr, en) olduğu için ortak 404 sayfası app/global-not-found.tsx'te.
  experimental: { globalNotFound: true },
};

export default config;
