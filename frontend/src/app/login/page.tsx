"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button, ErrorNote, Field, Input } from "@/components/ui";
import { login, tokens } from "@/lib/api";

function nextPath(): string {
  const next = new URLSearchParams(window.location.search).get("next") ?? "/";
  // Only same-site paths; never an absolute URL from the query string.
  return next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login") ? next : "/";
}

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (tokens.access()) router.replace(nextPath());
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
      router.replace(nextPath());
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen bg-surface lg:grid-cols-[1fr_1.1fr]">
      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <h1 className="text-3xl font-semibold tracking-tight text-ink">Welcome back</h1>
          <p className="mt-2 text-sm text-muted">Sign in to the Elix guardhouse and management console.</p>
          <form onSubmit={submit} className="mt-8 space-y-5">
            <ErrorNote error={error} />
            <Field label="Username">
              <Input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
            </Field>
            <Field label="Password">
              <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </Field>
            <Button type="submit" variant="primary" size="lg" className="w-full" busy={busy}>Sign in</Button>
          </form>
          <p className="mt-8 text-xs text-muted">Residents: please use the Elix mobile app.</p>
        </div>
      </div>
      <div className="brand-panel relative hidden flex-col justify-between overflow-hidden p-14 text-white lg:flex">
        <div className="pointer-events-none absolute inset-0 opacity-[0.07] [background-image:linear-gradient(rgb(255_255_255/0.6)_1px,transparent_1px),linear-gradient(90deg,rgb(255_255_255/0.6)_1px,transparent_1px)] [background-size:48px_48px]" />
        <div />
        <div className="relative">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/elix-logo.png" alt="Elix" className="w-72 drop-shadow-[0_0_30px_rgba(47,111,255,0.55)]" />
          <h2 className="mt-10 max-w-md text-2xl font-semibold leading-snug">Visitor management and access control for Singapore condominiums.</h2>
          <ul className="mt-6 space-y-2.5 text-sm text-slate-300">
            {["Licence-plate entry with Dahua LPR", "Video intercom with swipe-to-open", "QR invitations for visitors", "Shelly & Sonoff gate relays"].map((t) => (
              <li key={t} className="flex items-center gap-2.5">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary-500/25 text-primary-300">
                  <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth={3}><path d="M5 12l5 5L20 7" /></svg>
                </span>
                {t}
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-slate-500">© Elix PMS</p>
      </div>
    </main>
  );
}
