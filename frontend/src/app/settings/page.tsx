"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { apiBase, setApiBase, subscribeSettingsChange } from "@/lib/api";
import styles from "./settings.module.css";

interface RuntimeConfig {
  generation: {
    provider: string;
    model_id: string;
    base_url: string | null;
    think: unknown;
  };
  embedding: {
    provider: string;
    model_id: string;
    base_url: string | null;
    vector_dimensions: number | null;
  };
  qdrant_collection: string;
}

export default function SettingsPage() {
  const [baseInput, setBaseInput] = useState("");
  const [cfg, setCfg] = useState<RuntimeConfig | null>(null);
  const [cfgErr, setCfgErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const syncBaseFromStorage = useCallback(() => {
    setBaseInput(apiBase());
  }, []);

  useEffect(() => {
    syncBaseFromStorage();
    return subscribeSettingsChange(syncBaseFromStorage);
  }, [syncBaseFromStorage]);

  useEffect(() => {
    const b = baseInput.trim();
    if (!b) return;
    let cancelled = false;
    (async () => {
      setCfgErr(null);
      try {
        const res = await fetch(`${b}/v1/runtime-config`);
        if (!res.ok) throw new Error(res.statusText);
        const j = (await res.json()) as RuntimeConfig;
        if (!cancelled) setCfg(j);
      } catch (e) {
        if (!cancelled) {
          setCfgErr(e instanceof Error ? e.message : String(e));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [baseInput]);

  function onSaveApiBase(e: React.FormEvent) {
    e.preventDefault();
    setApiBase(baseInput.trim() || "http://127.0.0.1:8000");
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div className={styles.wrap}>
      <header className={styles.header}>
        <Link href="/" className={styles.back}>
          ← Home
        </Link>
        <h1 className={styles.title}>Settings</h1>
        <nav className={styles.navMini}>
          <Link href="/chat">Chat</Link>
          <Link href="/documents">Documents</Link>
        </nav>
      </header>

      <section className={styles.card}>
        <h2 className={styles.h2}>API 基址</h2>
        <p className={styles.lead}>
          前端所有 HTTP 与 WebSocket 请求使用该地址（写入 localStorage，刷新后仍生效）。
          切换模型需在服务器端编辑 <code>openagent.yaml</code> 并重启后端。
        </p>
        <form className={styles.form} onSubmit={onSaveApiBase}>
          <label className={styles.label} htmlFor="apiBase">
            NEXT_PUBLIC / 覆盖基址
          </label>
          <input
            id="apiBase"
            className={styles.input}
            value={baseInput}
            onChange={(e) => setBaseInput(e.target.value)}
            placeholder="http://127.0.0.1:8000"
          />
          <button type="submit" className={styles.btn}>
            保存
          </button>
        </form>
        {saved ? <p className={styles.ok}>已保存</p> : null}
      </section>

      <section className={styles.card}>
        <h2 className={styles.h2}>后端当前模型（只读）</h2>
        <p className={styles.lead}>
          来自 <code>GET /v1/runtime-config</code>，便于确认本机连接的是哪套配置。
        </p>
        {cfgErr ? (
          <p className={styles.error} role="alert">
            无法读取配置：{cfgErr}
          </p>
        ) : cfg ? (
          <dl className={styles.dl}>
            <dt>生成</dt>
            <dd>
              {cfg.generation.provider} / {cfg.generation.model_id}
            </dd>
            <dt>Base URL</dt>
            <dd>{cfg.generation.base_url ?? "—"}</dd>
            <dt>Embedding</dt>
            <dd>
              {cfg.embedding.provider} / {cfg.embedding.model_id}
            </dd>
            <dt>向量维度</dt>
            <dd>{cfg.embedding.vector_dimensions ?? "—"}</dd>
            <dt>Qdrant collection</dt>
            <dd>{cfg.qdrant_collection}</dd>
          </dl>
        ) : (
          <p className={styles.muted}>加载中…</p>
        )}
      </section>
    </div>
  );
}
