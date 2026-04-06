import type { ReactNode } from "react";
import { ChatProvider } from "@/stores/ChatProvider";

export default function ChatLayout({ children }: { children: ReactNode }) {
  return <ChatProvider>{children}</ChatProvider>;
}
