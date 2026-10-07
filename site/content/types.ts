export type Lang = "tr" | "en";

export type Check = { label: string; passed: boolean; counterexample?: string };

export type Round = {
  tab: string;
  verdict: string;
  accepted: boolean;
  addedLine: string;
  checks: Check[];
  stamp: string;
};

export type Dictionary = {
  lang: Lang;
  otherLang: { label: string; href: string };
  meta: { title: string; description: string };
  // Paylaşım görseli: alt metin ve görseldeki kısa etiket
  og: { alt: string; label: string };
  skipLink: string;
  nav: { label: string; record: string; how: string; demo: string; limits: string };
  // Bölüm başlıklarındaki küçük etiketler
  labels: {
    eyebrow: string;
    process: string;
    fieldRepo: string;
    fieldLive: string;
    scope: string;
    chapter: string;
    availability: string;
  };
  hero: { title: string; lede: string; cta: string; status: string };
  record: {
    label: string;
    // Bölüm başlığı ve kaydın kaynağı (gerçek Batfish çıktısı, kayıtlı öneriler)
    title: string;
    provenance: string;
    requestLabel: string;
    request: string;
    proved: string;
    violated: string;
    counterexample: string;
    tablistLabel: string;
    diffLabel: string;
    rounds: [Round, Round];
  };
  how: { title: string; steps: { title: string; body: string }[] };
  demo: {
    title: string;
    placeholder: string;
    body: string;
    commandLabel: string;
    setupLink: string;
    requestBody: string;
    requestLink: string;
    // Video varken: kaydın kaynağı ve video oynatılamazsa görünen metin
    videoNote: string;
    videoFallback: string;
    videoDownload: string;
  };
  proves: { title: string; items: string[] };
  limits: { title: string; items: string[] };
  closing: { title: string; body: string; cta: string; mailSubject: string };
  footer: { builtOn: string; and: string; source: string };
  notFound: { title: string; body: string; home: string };
};
