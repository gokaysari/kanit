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
  nav: { how: string; limits: string };
  hero: { title: string; lede: string; cta: string; status: string };
  record: {
    label: string;
    requestLabel: string;
    request: string;
    proved: string;
    violated: string;
    counterexample: string;
    rounds: [Round, Round];
  };
  how: { title: string; steps: { title: string; body: string }[] };
  proves: { title: string; items: string[] };
  limits: { title: string; items: string[] };
  closing: { title: string; body: string; cta: string };
  footer: { builtOn: string; and: string; source: string };
};
