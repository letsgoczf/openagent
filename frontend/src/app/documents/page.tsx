"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { apiBase, subscribeSettingsChange } from "@/lib/api";
import styles from "./documents.module.css";

interface DocumentRow {
  doc_id: string;
  file_name: string;
  file_type: string;
  doc_created_at: string;
  version_id: string | null;
  version_status: string | null;
  content_hash: string | null;
}

interface JobStatus {
  job_id: string;
  status: string;
  progress: Record<string, unknown>;
  error: string | null;
  doc_id: string | null;
  version_id: string | null;
}

export default function DocumentsPage() {
  const [file, setFile] = useState<File | null>(null);
  const [rows, setRows] = useState<DocumentRow[]>([]);
  const [listErr, setListErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [deletingDocId, setDeletingDocId] = useState<string | null>(null);
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<JobStatus | null>(null);

  const loadList = useCallback(async () => {
    setListErr(null);
    try {
      const res = await fetch(`${apiBase()}/v1/documents`);
      if (!res.ok) throw new Error(res.statusText);
      const data = (await res.json()) as DocumentRow[];
      setRows(Array.isArray(data) ? data : []);
    } catch (e) {
      setListErr(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void loadList();
    return subscribeSettingsChange(() => void loadList());
  }, [loadList]);

  async function pollJob(jobId: string) {
    for (let i = 0; i < 600; i++) {
      const res = await fetch(`${apiBase()}/v1/jobs/${jobId}`);
      if (!res.ok) break;
      const j = (await res.json()) as JobStatus;
      setActiveJob(j);
      if (j.status === "completed" || j.status === "failed") {
        await loadList();
        return;
      }
      await new Promise((r) => setTimeout(r, 700));
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setUploadErr(null);
    setActiveJob(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${apiBase()}/v1/documents/import`, {
        method: "POST",
        body: fd,
      });
      if (!res.ok) {
        const j = (await res.json().catch(() => ({}))) as {
          error?: { message?: string };
        };
        throw new Error(j.error?.message ?? res.statusText);
      }
      const data = (await res.json()) as { job_id: string };
      void pollJob(data.job_id);
    } catch (e) {
      setUploadErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(doc: DocumentRow) {
    const ok = window.confirm(`确认删除文档「${doc.file_name}」？此操作不可恢复。`);
    if (!ok) return;
    setDeletingDocId(doc.doc_id);
    setListErr(null);
    try {
      const res = await fetch(`${apiBase()}/v1/documents/${doc.doc_id}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const j = (await res.json().catch(() => ({}))) as {
          error?: { message?: string };
        };
        throw new Error(j.error?.message ?? res.statusText);
      }
      await loadList();
    } catch (e) {
      setListErr(e instanceof Error ? e.message : String(e));
    } finally {
      setDeletingDocId(null);
    }
  }

  const prog = activeJob?.progress as {
    page?: number;
    total_pages?: number;
    processed_chunks?: number;
  } | undefined;

  return (
    <div className={styles.wrap}>
      <header className={styles.header}>
        <Link href="/" className={styles.back}>
          ← Home
        </Link>
        <h1 className={styles.title}>Documents</h1>
        <nav className={styles.navMini}>
          <Link href="/chat">Chat</Link>
          <Link href="/settings">Settings</Link>
        </nav>
      </header>
      <p className={styles.lead}>
        上传常见办公与文本类文件后后台异步入库（PDF、Office、RTF、HTML、CSV/JSON/YAML、ODT、EPUB、邮件
        .eml、源码与纯文本等）；下方列表来自 SQLite，可查看版本状态。
      </p>

      <form className={styles.form} onSubmit={onSubmit}>
        <label className={styles.label} htmlFor="doc">
          选择文件
        </label>
        <input
          id="doc"
          type="file"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !file}>
          {busy ? "上传中…" : "导入"}
        </button>
      </form>

      {uploadErr ? (
        <p className={styles.error} role="alert">
          {uploadErr}
        </p>
      ) : null}

      {activeJob ? (
        <section className={styles.jobCard} aria-live="polite">
          <h2 className={styles.jobTitle}>当前任务</h2>
          <p>
            <code>job_id</code>：{activeJob.job_id}
          </p>
          <p>
            状态：<strong>{activeJob.status}</strong>
          </p>
          {activeJob.status === "processing" && prog?.total_pages ? (
            <p className={styles.progress}>
              页进度：{prog.page ?? 0} / {prog.total_pages}
              {typeof prog.processed_chunks === "number"
                ? ` · 已写入块 ${prog.processed_chunks}`
                : ""}
            </p>
          ) : null}
          {activeJob.status === "failed" && activeJob.error ? (
            <p className={styles.error}>{activeJob.error}</p>
          ) : null}
          {activeJob.status === "completed" ? (
            <p className={styles.ok}>
              完成
              {activeJob.doc_id ? ` · doc ${activeJob.doc_id.slice(0, 8)}…` : ""}
            </p>
          ) : null}
        </section>
      ) : null}

      <section className={styles.listSection}>
        <h2 className={styles.listTitle}>文档列表</h2>
        {listErr ? (
          <p className={styles.error}>{listErr}</p>
        ) : rows.length === 0 ? (
          <p className={styles.muted}>暂无文档</p>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>文件名</th>
                <th>类型</th>
                <th>版本状态</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.doc_id}>
                  <td>{r.file_name}</td>
                  <td>{r.file_type}</td>
                  <td>{r.version_status ?? "—"}</td>
                  <td className={styles.monoSmall}>{r.doc_created_at}</td>
                  <td>
                    <button
                      type="button"
                      className={styles.deleteBtn}
                      onClick={() => void onDelete(r)}
                      disabled={deletingDocId === r.doc_id}
                    >
                      {deletingDocId === r.doc_id ? "删除中…" : "删除"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
