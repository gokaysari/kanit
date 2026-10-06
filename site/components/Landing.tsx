import type { Dictionary } from "@/content/types";
import { site } from "@/site.config";

import { ChangeRecord } from "./ChangeRecord";
import { DemoSlot } from "./DemoSlot";
import styles from "./Landing.module.css";

function mailto(subject: string) {
  return `mailto:${site.email}?subject=${encodeURIComponent(subject)}`;
}

export function Landing({ dict }: { dict: Dictionary }) {
  const otherLang = dict.lang === "tr" ? "en" : "tr";
  return (
    <>
      <a className={styles.skip} href="#main">
        {dict.skipLink}
      </a>
      <header className={`${styles.wrap} ${styles.top}`}>
        <div className={styles.mark}>
          {site.name}
          <span>.</span>
        </div>
        <nav className={styles.nav} aria-label={dict.nav.label}>
          <a href="#how">{dict.nav.how}</a>
          <a href="#demo">{dict.nav.demo}</a>
          <a href="#limits">{dict.nav.limits}</a>
          <a
            className={styles.lang}
            href={dict.otherLang.href}
            hrefLang={otherLang}
            lang={otherLang}
          >
            {dict.otherLang.label}
          </a>
        </nav>
      </header>

      <main id="main" tabIndex={-1}>
        <div className={`${styles.wrap} ${styles.hero}`}>
          <div>
            <h1 className={styles.title}>{dict.hero.title}</h1>
            <p className={styles.lede}>{dict.hero.lede}</p>
            <a className={styles.cta} href={mailto(`${site.name} demo`)}>
              {dict.hero.cta}
            </a>
            <p className={styles.status}>{dict.hero.status}</p>
          </div>
          <ChangeRecord record={dict.record} />
        </div>

        <section className={styles.band} id="how">
          <div className={styles.wrap}>
            <h2 className={styles.heading}>{dict.how.title}</h2>
            <ol className={styles.steps}>
              {dict.how.steps.map((step) => (
                <li key={step.title}>
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className={styles.band} id="demo" aria-labelledby="demo-title">
          <div className={styles.wrap}>
            <h2 className={styles.heading} id="demo-title">
              {dict.demo.title}
            </h2>
            <DemoSlot demo={dict.demo} />
          </div>
        </section>

        <section className={styles.band} id="limits">
          <div className={`${styles.wrap} ${styles.cols}`}>
            {[dict.proves, dict.limits].map((col) => (
              <div key={col.title}>
                <h2 className={styles.heading}>{col.title}</h2>
                <ul>
                  {col.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        <section className={styles.band}>
          <div className={styles.wrap}>
            <h2 className={styles.heading}>{dict.closing.title}</h2>
            <p className={styles.closing}>{dict.closing.body}</p>
            <a className={styles.cta} href={mailto(`${site.name} pilot`)}>
              {dict.closing.cta}
            </a>
          </div>
        </section>
      </main>

      <footer className={styles.footer}>
        <div className={styles.wrap}>
          {dict.footer.builtOn} <a href={site.batfish}>Batfish</a> {dict.footer.and}{" "}
          <a href={site.repo}>{dict.footer.source}</a>
        </div>
      </footer>
    </>
  );
}
