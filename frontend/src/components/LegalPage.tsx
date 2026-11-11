"use client";

import { Credit } from "./Credit";

/** Public page (privacy, cybersecurity, account deletion) linked from the login page, Google Play and the resident app. */
export function LegalPage({ title, updated, children }: { title: string; updated: string; children: React.ReactNode }) {
  return (
    <div className="min-h-dvh bg-canvas">
      <div className="brand-panel px-6 pb-24 pt-8 text-white">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/brand/elix-logo.png" alt="Elix" className="mx-auto h-8 w-auto drop-shadow-[0_0_14px_rgba(47,111,255,0.5)]" />
      </div>
      <main className="mx-auto -mt-16 max-w-3xl px-4 pb-10">
        <article className="rounded-2xl border border-line bg-surface p-6 text-sm leading-relaxed text-body shadow-card sm:p-8 [&_a]:text-primary-500 [&_a]:underline [&_h2]:mb-2 [&_h2]:mt-7 [&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-ink [&_li]:mt-1 [&_p]:mt-3 [&_ul]:mt-2 [&_ul]:list-disc [&_ul]:pl-5">
          <h1 className="text-xl font-semibold text-ink">{title}</h1>
          <p className="!mt-1 text-xs text-muted">Last updated {updated}</p>
          {children}
        </article>
        <Credit className="mt-8" />
      </main>
    </div>
  );
}
