import type { Dictionary, Lang } from "@/content/types";
import { site } from "@/site.config";

import styles from "./DemoSlot.module.css";
import { DemoVideo } from "./DemoVideo";

// Demoyu yerelde çalıştıran komut; Makefile'daki hedeflerle aynı.
const COMMAND = "make setup && make demo";

export function DemoSlot({
  demo,
  lang,
  requestHref,
}: {
  demo: Dictionary["demo"];
  lang: Lang;
  requestHref: string;
}) {
  const video = site.demoVideo;
  // MP4 (H.264) varsa önce o denenir; WebM yalnızca VP9 oynatabilen tarayıcılarda çalışır.
  const sources = [
    ...(site.demoVideoMp4 ? [{ src: site.demoVideoMp4, type: "video/mp4" }] : []),
    ...(video ? [{ src: video, type: "video/webm" }] : []),
  ];

  return (
    <div className={styles.slot}>
      {video ? (
        <DemoVideo
          sources={sources}
          poster={site.demoPoster}
          captions={site.demoCaptions}
          lang={lang}
          label={demo.title}
          fallback={demo.videoFallback}
          download={demo.videoDownload}
        />
      ) : (
        // Kayıt yokken boş bir oynatıcı göstermek yerine bunu açıkça söyleriz.
        <div className={`${styles.frame} ${styles.empty}`}>
          <p>{demo.placeholder}</p>
        </div>
      )}

      {site.repo ? (
        <div className={styles.text}>
          {video && <p className={styles.note}>{demo.videoNote}</p>}
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
          {video && <p className={styles.note}>{demo.videoNote}</p>}
          <p>{demo.requestBody}</p>
          <a href={requestHref}>{demo.requestLink}</a>
        </div>
      )}
    </div>
  );
}
