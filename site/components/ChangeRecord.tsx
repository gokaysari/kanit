"use client";

import { useId, useRef, useState, type KeyboardEvent } from "react";

import { ACL_AFTER, ACL_BEFORE } from "@/content/record";
import type { Dictionary } from "@/content/types";

import styles from "./ChangeRecord.module.css";

export function ChangeRecord({ record }: { record: Dictionary["record"] }) {
  const [active, setActive] = useState(0);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const id = useId();
  const round = record.rounds[active];

  function onKeyDown(event: KeyboardEvent) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    const step = event.key === "ArrowRight" ? 1 : record.rounds.length - 1;
    const next = (active + step) % record.rounds.length;
    setActive(next);
    tabs.current[next]?.focus();
  }

  return (
    <div className={styles.record} role="group" aria-label={record.label}>
      <div className={styles.request}>
        <small>{record.requestLabel}</small>
        <p>{record.request}</p>
      </div>

      <div className={styles.tabs} role="tablist" onKeyDown={onKeyDown}>
        {record.rounds.map((r, i) => (
          <button
            key={r.tab}
            ref={(el) => {
              tabs.current[i] = el;
            }}
            type="button"
            role="tab"
            id={`${id}-tab-${i}`}
            aria-controls={`${id}-panel`}
            aria-selected={i === active}
            tabIndex={i === active ? 0 : -1}
            onClick={() => setActive(i)}
          >
            {r.tab}
            <b className={r.accepted ? styles.ok : styles.no}>{r.verdict}</b>
          </button>
        ))}
      </div>

      <div
        className={styles.panel}
        role="tabpanel"
        id={`${id}-panel`}
        aria-labelledby={`${id}-tab-${active}`}
      >
        <pre className={styles.diff}>
          {ACL_BEFORE.join("\n") + "\n"}
          <span className={round.accepted ? styles.addOk : styles.addNo}>{round.addedLine}</span>
          {ACL_AFTER.join("\n")}
        </pre>

        <ul className={styles.checks}>
          {round.checks.map((check) => (
            <li key={check.label} className={check.passed ? styles.pass : styles.fail}>
              <span>{check.label}</span>
              <span className={styles.result}>{check.passed ? record.proved : record.violated}</span>
              {check.counterexample && (
                <span className={styles.counter}>
                  {record.counterexample}: {check.counterexample}
                </span>
              )}
            </li>
          ))}
        </ul>

        {/* key: sekme değişince damga animasyonu yeniden oynar */}
        <div key={active} className={`${styles.stamp} ${round.accepted ? styles.ok : styles.no}`}>
          {round.stamp}
        </div>
      </div>
    </div>
  );
}
