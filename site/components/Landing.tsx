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
  const labels = dict.labels;

  return (
    <div className={styles.page}>
      <a className={styles.skip} href="#main">
        {dict.skipLink}
      </a>
      <header className={styles.top}>
        <a className={styles.mark} href={dict.lang === "tr" ? "/" : "/en/"} aria-label={site.name}>
          <span className={styles.markGlyph}>N</span>
          <span>{site.name}</span>
        </a>
        {/* Dar ekranda bölüm bağlantıları ikinci satırda yatay kaydırılır; JS gerekmez. */}
        <nav className={styles.nav} aria-label={dict.nav.label}>
          <a href="#record">01 — {dict.nav.record}</a>
          <a href="#how">02 — {dict.nav.how}</a>
          <a href="#demo">03 — {dict.nav.demo}</a>
          <a href="#limits">04 — {dict.nav.limits}</a>
        </nav>
        <a
          className={styles.lang}
          href={dict.otherLang.href}
          hrefLang={otherLang}
          lang={otherLang}
        >
          {dict.otherLang.label}
        </a>
      </header>

      <main id="main" tabIndex={-1}>
        <section className={styles.hero}>
          <div className={styles.heroGrid}>
            <p className={styles.eyebrow}>
              <span>{site.name.toUpperCase()}</span>
              <span>2026 — 001</span>
            </p>
            <h1 className={styles.title}>{dict.hero.title}</h1>
            <div className={styles.heroFoot}>
              <p className={styles.heroIndex}>[ N / 01 ]</p>
              <div>
                <p className={styles.lede}>{dict.hero.lede}</p>
                <div className={styles.heroActions}>
                  <a className={styles.cta} href={mailto(`${site.name} demo`)}>
                    {dict.hero.cta}<span aria-hidden="true">↗</span>
                  </a>
                  <p className={styles.status}>
                    <span className={styles.pulse} aria-hidden="true" />
                    {dict.hero.status}
                  </p>
                </div>
              </div>
            </div>
          </div>
          <div className={styles.heroRail} aria-hidden="true">
            <span>{labels.eyebrow}</span>
            <span>SCROLL ↓</span>
          </div>
        </section>

        <section className={`${styles.band} ${styles.recordBand}`} id="record">
          <div className={styles.sectionHead}>
            <p>01 / {labels.chapter}</p>
            <h2>{dict.record.title}</h2>
            <p>{dict.record.request}</p>
          </div>
          <p className={styles.provenance}>{dict.record.provenance}</p>
          <ChangeRecord record={dict.record} />
        </section>

        <section className={styles.band} id="how">
          <div className={styles.sectionHead}>
            <p>02 / {labels.chapter}</p>
            <h2>{dict.how.title}</h2>
            <p>{labels.process}</p>
          </div>
          <div className={styles.processGrid}>
            <div className={styles.processStatement}>
              <span>REQUEST</span>
              <strong>{dict.record.request}</strong>
              <span className={styles.processArrow} aria-hidden="true">↓</span>
              <span>VERIFIED CHANGE</span>
            </div>
            <ol className={styles.steps}>
              {dict.how.steps.map((step, index) => (
                <li key={step.title}>
                  <span className={styles.stepNo}>0{index + 1}</span>
                  <div>
                    <h3>{step.title}</h3>
                    <p>{step.body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className={`${styles.band} ${styles.demoBand}`} id="demo" aria-labelledby="demo-title">
          <div className={styles.sectionHead}>
            <p>03 / {labels.chapter}</p>
            <h2 id="demo-title">{dict.demo.title}</h2>
            <p>{site.repo ? labels.fieldRepo : labels.fieldLive}</p>
          </div>
          <div className={styles.demoInner}>
            <DemoSlot demo={dict.demo} lang={dict.lang} requestHref={mailto(`${site.name} demo`)} />
          </div>
        </section>

        <section className={`${styles.band} ${styles.scopeBand}`} id="limits">
          <div className={styles.sectionHead}>
            <p>04 / {labels.chapter}</p>
            <h2>{labels.scope}</h2>
            <p>{dict.nav.limits}</p>
          </div>
          <div className={styles.cols}>
            {[dict.proves, dict.limits].map((col, index) => (
              <div key={col.title} className={index === 0 ? styles.positive : styles.negative}>
                <span className={styles.colSign} aria-hidden="true">{index === 0 ? "+" : "−"}</span>
                <h3>{col.title}</h3>
                <ul>
                  {col.items.map((item, itemIndex) => (
                    <li key={item}><span>0{itemIndex + 1}</span>{item}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        <section className={`${styles.band} ${styles.closingBand}`}>
          <div>
            <p className={styles.availability}><span className={styles.pulse} />{labels.availability}</p>
            <h2>{dict.closing.title}</h2>
            <p className={styles.closing}>{dict.closing.body}</p>
            <a className={`${styles.cta} ${styles.ctaLight}`} href={mailto(`${site.name} pilot`)}>
              {dict.closing.cta}
              <span aria-hidden="true">↗</span>
            </a>
          </div>
          <a className={styles.bigMail} href={mailto(`${site.name} ${dict.closing.mailSubject}`)}>{site.email}</a>
        </section>
      </main>

      <footer className={styles.footer}>
        <div>
          <span>© {new Date().getFullYear()} {site.name}</span>
          <span>
          {dict.footer.builtOn} <a href={site.batfish} lang="en">Batfish</a> {dict.footer.and}
          {site.repo && <> <a href={site.repo}>{dict.footer.source}</a></>}
          </span>
        </div>
      </footer>
    </div>
  );
}
