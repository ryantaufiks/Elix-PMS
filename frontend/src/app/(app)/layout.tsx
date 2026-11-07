"use client";

import { Shell } from "@/components/Shell";
import { LiveProvider } from "@/lib/live";
import { SessionProvider } from "@/lib/session";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <LiveProvider>
        <Shell>{children}</Shell>
      </LiveProvider>
    </SessionProvider>
  );
}
