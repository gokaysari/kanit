import type { NextConfig } from "next";

// Statik çıktı: `npm run build` sonrası `out/` klasörü herhangi bir statik sunucuya konabilir.
const config: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default config;
