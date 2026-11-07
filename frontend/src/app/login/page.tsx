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
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center justify-center gap-2">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-700 text-lg font-bold text-white">E</span>
          <span className="text-xl font-semibold text-slate-900">Elix PMS</span>
        </div>
        <form onSubmit={submit} className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div>
            <h1 className="text-lg font-semibold text-slate-900">Staff sign in</h1>
            <p className="mt-1 text-sm text-slate-500">Guardhouse and management dashboard</p>
          </div>
          <ErrorNote error={error} />
          <Field label="Username">
            <Input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
          </Field>
          <Field label="Password">
            <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </Field>
          <Button type="submit" variant="primary" className="w-full" busy={busy}>Sign in</Button>
        </form>
      </div>
    </main>
  );
}
