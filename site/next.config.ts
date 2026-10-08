import type { NextConfig } from "next";

// Güvenlik başlıkları. Aynı küme public/_headers'ta da var: Workers'ta statik varlıklar
// (video, görsel, /_next/static) worker'a uğramadan sunulur ve yalnızca _headers'ı görür;
// sayfalar ise worker'da üretilir ve bu headers() kurallarını alır.
// Satır içi betik izni gerekli: vinext RSC yükünü sayfaya satır içi <script> olarak gömer.
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self' data:",
  "media-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const securityHeaders = [
  { key: "Strict-Transport-Security", value: "max-age=31536000" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Content-Security-Policy", value: CSP },
];

const config: NextConfig = {
  async headers() {
    // vinext'te "/:path*" kök yolu (/) kapsamıyor; kök ayrıca yazılır.
    return [
      { source: "/", headers: securityHeaders },
      { source: "/:path*", headers: securityHeaders },
    ];
  },
  trailingSlash: true,
  images: { unoptimized: true },
  // İki ayrı kök düzen (tr, en) olduğu için ortak 404 sayfası app/global-not-found.tsx'te.
  experimental: { globalNotFound: true },
};

export default config;
