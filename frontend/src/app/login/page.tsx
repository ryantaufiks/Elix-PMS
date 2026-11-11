"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Icon, type IconName } from "@/components/icons";
import { Button, ErrorNote, Input } from "@/components/ui";
import { login, tokens } from "@/lib/api";
import { Credit } from "@/components/Credit";

/** Login field: rounded, with a leading icon and an optional control at the end (show password). */
function LoginField({ id, label, icon, end, ...props }: React.ComponentProps<"input"> & { id: string; label: string; icon: IconName; end?: React.ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-ink">{label}</label>
      <div className="relative">
        <Icon name={icon} className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-muted" />
        <Input id={id} {...props} className={`!h-12 !rounded-xl !bg-surface-2 !pl-12 !text-base transition focus:!bg-surface ${end ? "!pr-12" : "!pr-4"}`} />
        {end && <div className="absolute right-2 top-1/2 -translate-y-1/2">{end}</div>}
      </div>
    </div>
  );
}

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
  const [show, setShow] = useState(false);

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
    <main className="flex min-h-dvh flex-col bg-canvas lg:grid lg:grid-cols-[1fr_1.1fr] lg:bg-surface">
      {/* Phones and tablets: the brand on top, the form in a card over it. */}
      <div className="brand-panel px-6 pb-24 pt-12 text-center text-white sm:pt-16 lg:hidden">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/brand/elix-logo.png" alt="Elix" className="mx-auto h-12 w-auto drop-shadow-[0_0_24px_rgba(47,111,255,0.55)] sm:h-16" />
        <p className="mx-auto mt-4 max-w-xs text-sm text-slate-300 sm:max-w-md sm:text-base">Visitor management and access control for Singapore condominiums.</p>
      </div>
      <div className="-mt-16 flex flex-1 flex-col items-center px-4 pb-8 sm:px-6 lg:mt-0 lg:justify-center lg:py-12">
        <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-6 shadow-card sm:p-8 lg:max-w-sm lg:border-0 lg:p-0 lg:shadow-none">
          <h1 className="text-center text-2xl font-semibold tracking-tight text-ink sm:text-3xl lg:text-left">Welcome back</h1>
          <p className="mt-2 text-center text-sm text-muted lg:text-left">Sign in to the Elix guardhouse and management console.</p>
          <form onSubmit={submit} className="mt-8 space-y-5">
            <ErrorNote error={error} />
            <LoginField id="username" label="Username" icon="user" autoComplete="username" value={username}
              onChange={(e) => setUsername(e.target.value)} required autoFocus />
            <LoginField id="password" label="Password" icon="lock" type={show ? "text" : "password"} autoComplete="current-password"
              value={password} onChange={(e) => setPassword(e.target.value)} required
              end={
                <button type="button" onClick={() => setShow((v) => !v)} aria-label={show ? "Hide password" : "Show password"}
                  className="flex h-9 w-9 items-center justify-center rounded-lg text-muted transition hover:bg-surface-3 hover:text-ink">
                  <Icon name={show ? "eyeOff" : "eye"} className="h-5 w-5" />
                </button>
              } />
            <Button type="submit" variant="primary" size="lg" className="w-full !rounded-xl" busy={busy}>Sign in</Button>
          </form>
          <p className="mt-8 text-center text-xs text-muted lg:text-left">Residents: please use the Elix mobile app.</p>
          <p className="mt-3 flex justify-center gap-4 text-xs text-muted lg:justify-start">
            <a href="/privacy/" className="hover:text-primary-500 hover:underline">Privacy policy</a>
            <a href="/security/" className="hover:text-primary-500 hover:underline">Cybersecurity policy</a>
          </p>
        </div>
        <Credit className="mt-8 lg:hidden" />
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
        <Credit tone="dark" align="left" className="relative" />
      </div>
    </main>
  );
}
