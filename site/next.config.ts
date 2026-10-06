import type { NextConfig } from "next";

// Statik çıktı: `npm run build` sonrası `out/` klasörü herhangi bir statik sunucuya konabilir.
const config: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  // İki ayrı kök düzen (tr, en) olduğu için ortak 404 sayfası app/global-not-found.tsx'te.
  experimental: { globalNotFound: true },
};

export default config;
