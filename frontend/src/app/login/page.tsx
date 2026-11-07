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
    <main className="grid min-h-screen bg-white lg:grid-cols-2">
      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-10 flex items-center gap-2.5">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-500 text-lg font-bold text-white shadow-primary">E</span>
            <span className="text-2xl font-semibold tracking-tight text-ink">Elix PMS</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight text-ink">Sign in</h1>
          <p className="mt-2 text-sm text-muted">Guardhouse and management dashboard.</p>
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
      <div className="hero-band relative hidden overflow-hidden lg:flex lg:items-end">
        <div className="relative p-14 text-white">
          <h2 className="text-3xl font-semibold leading-tight">Visitors, vehicles and gates,<br />in one place.</h2>
          <p className="mt-3 max-w-md text-white/80">Licence-plate entry, video intercom with swipe-to-open, and QR invitations for Singapore condominiums.</p>
        </div>
      </div>
    </main>
  );
}
