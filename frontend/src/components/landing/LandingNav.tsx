"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { tokens } from "@/lib/api";
import { cx } from "@/components/ui";

export const DEMO_MAIL = "mailto:services@smartcitytechnologies.com.sg?subject=" + encodeURIComponent("Elix demo request")
  + "&body=" + encodeURIComponent("Hello Elix team,\n\nWe would like a demo.\n\nCondominium:\nNumber of units:\nNumber of gates:\nContact person and phone:\n");

const LINKS = [
  ["#features", "Features"], ["#how", "How it works"], ["#plans", "Plans"], ["#pdpa", "PDPA"], ["#security", "Security"],
] as const;

/** Top bar: section links, and Sign in (or Open dashboard when already signed in on this browser). */
export function LandingNav() {
  const [signedIn, setSignedIn] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    setSignedIn(!!tokens.refresh());
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return (
    <header className={cx("fixed inset-x-0 top-0 z-40 transition-colors", scrolled ? "border-b border-white/10 bg-navy-950/85 backdrop-blur" : "bg-transparent")}>
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 sm:px-6">
        <a href="#top" className="shrink-0">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/elix-logo.png" alt="Elix" className="h-7 w-auto drop-shadow-[0_0_12px_rgba(47,111,255,0.5)]" />
        </a>
        <nav className="hidden flex-1 items-center gap-1 md:flex">
          {LINKS.map(([href, label]) => (
            <a key={href} href={href} className="rounded-md px-3 py-2 text-sm text-slate-300 transition hover:bg-white/5 hover:text-white">{label}</a>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <Link href={signedIn ? "/dashboard/" : "/login/"} className="rounded-lg px-3 py-2 text-sm font-medium text-slate-200 hover:bg-white/5 hover:text-white">
            {signedIn ? "Open dashboard" : "Sign in"}
          </Link>
          <a href={DEMO_MAIL} className="hidden rounded-lg bg-primary-500 px-4 py-2 text-sm font-semibold text-white shadow-primary transition hover:bg-primary-600 sm:inline-block">
            Request a demo
          </a>
        </div>
      </div>
    </header>
  );
}
