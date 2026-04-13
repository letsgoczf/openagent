"use client";

import { useMemo } from "react";
import type { CitationDTO } from "@/types/chat";
import styles from "./CitationInlineText.module.css";

type Part =
  | { kind: "text"; value: string }
  | { kind: "cite"; n: number; chunkId: string };

function buildParts(text: string, citations: CitationDTO[] | undefined): Part[] {
  if (!text) {
    return [];
  }
  const re = /\[(\d+)\]/g;
  const parts: Part[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      parts.push({ kind: "text", value: text.slice(last, m.index) });
    }
    const n = Number.parseInt(m[1], 10);
    const cite =
      citations && n >= 1 && n <= citations.length ? citations[n - 1] : null;
    if (cite) {
      parts.push({ kind: "cite", n, chunkId: cite.chunk_id });
    } else {
      parts.push({ kind: "text", value: m[0] });
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) {
    parts.push({ kind: "text", value: text.slice(last) });
  }
  return parts.length > 0 ? parts : [{ kind: "text", value: text }];
}

export function CitationInlineText(props: {
  text: string;
  citations: CitationDTO[] | undefined;
  onCiteClick: (chunkId: string) => void;
}) {
  const { text, citations, onCiteClick } = props;

  const parts = useMemo(() => buildParts(text, citations), [text, citations]);

  return (
    <>
      {parts.map((p, i) =>
        p.kind === "text" ? (
          <span key={`t-${i}`} className={styles.textSeg}>
            {p.value}
          </span>
        ) : (
          <button
            key={`c-${i}-${p.chunkId}`}
            type="button"
            className={styles.citeInline}
            title="在侧栏定位证据"
            onClick={() => onCiteClick(p.chunkId)}
          >
            [{p.n}]
          </button>
        )
      )}
    </>
  );
}
