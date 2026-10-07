"use client";

import { useEffect, useRef, useState } from "react";

import type { Lang } from "@/content/types";

import styles from "./DemoSlot.module.css";

type Props = {
  // Tarayıcı ilk oynatabildiğini seçer; MP4 eklenirse WebM'den önce gelir.
  sources: { src: string; type: string }[];
  poster: string;
  captions: Record<Lang, string>;
  lang: Lang;
  label: string;
  fallback: string;
  download: string;
};

const CAPTION_LABEL: Record<Lang, string> = { tr: "Türkçe", en: "English" };

export function DemoVideo({ sources, poster, captions, lang, label, fallback, download }: Props) {
  const ref = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    // Hidrasyondan önce tüm kaynaklar düşmüşse (ör. iOS'ta WebM) hata olayı kaçmış olabilir.
    if (ref.current?.networkState === HTMLMediaElement.NETWORK_NO_SOURCE) setFailed(true);
  }, []);

  // Sayfanın dili önce ve varsayılan; diğer dil menüden seçilebilir.
  const langs: Lang[] = lang === "tr" ? ["tr", "en"] : ["en", "tr"];
  const last = sources.length - 1;

  return (
    <figure className={styles.figure}>
      <video
        ref={ref}
        className={styles.frame}
        controls
        playsInline
        preload="metadata"
        poster={poster}
        width={1280}
        height={720}
        aria-label={label}
      >
        {sources.map((s, i) => (
          <source
            key={s.src}
            src={s.src}
            type={s.type}
            // Son kaynak da düşerse tarayıcı bu videoyu oynatamıyor demektir.
            onError={i === last ? () => setFailed(true) : undefined}
          />
        ))}
        {langs.map((l) => (
          <track
            key={l}
            kind="captions"
            src={captions[l]}
            srcLang={l}
            label={CAPTION_LABEL[l]}
            default={l === lang}
          />
        ))}
        <p>
          {fallback} <a href={sources[last].src}>{download}</a>
        </p>
      </video>
      {failed && (
        <figcaption className={styles.fallback} role="status">
          {fallback} <a href={sources[last].src} download>{download}</a>
        </figcaption>
      )}
    </figure>
  );
}
