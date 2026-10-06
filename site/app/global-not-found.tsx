// Statik sunucu her eşleşmeyen adres için tek bir 404.html döndürür; ziyaretçinin dilini
// bilemeyiz, bu yüzden sayfa iki dili birlikte gösterir.
import type { Metadata } from "next";

import "./styles";
import { en } from "@/content/en";
import { tr } from "@/content/tr";
import { site } from "@/site.config";

import styles from "./not-found.module.css";

export const metadata: Metadata = {
  title: `404 · ${tr.notFound.title} · ${site.name}`,
  robots: { index: false },
};

export default function GlobalNotFound() {
  return (
    <html lang="tr">
      <body>
        <main className={styles.page}>
          <a className={styles.mark} href="/">
            {site.name}
            <span>.</span>
          </a>
          <p className={styles.code} aria-hidden="true">
            404
          </p>
          <div className={styles.cols}>
            {[tr, en].map((dict) => (
              <section key={dict.lang} lang={dict.lang}>
                <h1 className={styles.title}>{dict.notFound.title}</h1>
                <p className={styles.body}>{dict.notFound.body}</p>
                <a href={dict.lang === "tr" ? "/" : "/en/"}>{dict.notFound.home}</a>
              </section>
            ))}
          </div>
        </main>
      </body>
    </html>
  );
}
