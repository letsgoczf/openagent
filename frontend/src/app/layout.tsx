import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OpenAgent",
  description: "Local agent assistant — streaming chat, documents, retrieval & tool trace",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-Hans">
      <body>{children}</body>
    </html>
  );
}
