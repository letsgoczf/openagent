import Link from "next/link";
import styles from "./page.module.css";

export default function HomePage() {
  return (
    <main className={styles.main}>
      <a href="#content" className={styles.skip}>
        Skip to content
      </a>
      <header className={styles.header}>
        <span className={styles.brand}>OpenAgent</span>
        <nav className={styles.nav} aria-label="Primary">
          <Link href="/chat">Chat</Link>
          <Link href="/documents">Documents</Link>
          <Link href="/settings">Settings</Link>
        </nav>
      </header>
      <section id="content" className={styles.hero}>
        <h1 className={styles.h1}>本地智能体助手</h1>
        <p className={styles.lead}>
          上传 PDF、通过 WebSocket 与智能体流式对话；侧栏可查看知识检索、工具调用与执行追踪。
        </p>
        <div className={styles.cta}>
          <Link className={styles.primary} href="/chat">
            进入对话
          </Link>
          <Link className={styles.secondary} href="/documents">
            文档导入
          </Link>
        </div>
      </section>
      <footer className={styles.footer}>
        <span>后端默认 {`http://127.0.0.1:8000`} · 可用环境变量 NEXT_PUBLIC_API_BASE 覆盖</span>
      </footer>
    </main>
  );
}
