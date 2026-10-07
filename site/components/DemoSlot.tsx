import type { Dictionary } from "@/content/types";
import { site } from "@/site.config";

import styles from "./DemoSlot.module.css";

// Demoyu yerelde çalıştıran komut; Makefile'daki hedeflerle aynı.
const COMMAND = "make setup && make demo";

export function DemoSlot({ demo, requestHref }: { demo: Dictionary["demo"]; requestHref: string }) {
  const video = site.demoVideo;

  return (
    <div className={styles.slot}>
      {video ? (
        <video className={styles.frame} src={video} controls preload="metadata" />
      ) : (
        // Kayıt yokken boş bir oynatıcı göstermek yerine bunu açıkça söyleriz.
        <div className={`${styles.frame} ${styles.empty}`}>
          <p>{demo.placeholder}</p>
        </div>
      )}

      {site.repo ? (
        <div className={styles.text}>
          <p>{demo.body}</p>
          <p className={styles.commandLabel}>{demo.commandLabel}</p>
          <pre className={styles.command}>
            <code>{COMMAND}</code>
          </pre>
          <a href={`${site.repo}#readme`}>{demo.setupLink}</a>
        </div>
      ) : (
        // Repo herkese açık değilken ziyaretçi komutu çalıştıramaz; canlı gösterim öneririz.
        <div className={styles.text}>
          <p>{demo.requestBody}</p>
          <a href={requestHref}>{demo.requestLink}</a>
        </div>
      )}
    </div>
  );
}
