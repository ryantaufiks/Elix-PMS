"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { api, LOGOUT_EVENT, logout as clearTokens, tokens } from "./api";
import { Onboarding } from "@/components/Onboarding";

import type { Condominium, Me, Page, Role } from "./types";

type Session = {
  me: Me;
  condos: Condominium[];
  condo: Condominium;
  role: Role;
  isAdmin: boolean;
  selectCondo: (id: number) => void;
  /** Re-read the user and their condominiums (after adding or renaming a site). */
  reload: () => Promise<void>;
  logout: () => void;
};

const SessionContext = createContext<Session | null>(null);
const CONDO_KEY = "elix.condo";

function roleFor(me: Me, condoId: number): Role | null {
  if (me.is_superuser) return "admin";
  const roles = me.staff_assignments.filter((a) => a.condominium === condoId).map((a) => a.role);
  return roles.includes("admin") ? "admin" : roles.includes("security") ? "security" : null;
}

type State =
  | { status: "loading" }
  | { status: "ready"; me: Me; condos: Condominium[] }
  | { status: "no-access" }
  | { status: "no-condo" }
  | { status: "error"; message: string };

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [state, setState] = useState<State>({ status: "loading" });
  const [condoId, setCondoId] = useState<number | null>(null);

  const logout = useCallback(() => {
    clearTokens();
  }, []);

  useEffect(() => {
    const onLogout = () => router.replace("/login/");
    window.addEventListener(LOGOUT_EVENT, onLogout);
    return () => window.removeEventListener(LOGOUT_EVENT, onLogout);
  }, [router]);

  const load = useCallback(async (isCancelled: () => boolean = () => false) => {
      try {
        const me = await api<Me>("/v1/auth/me/");
        if (!me.is_superuser && me.staff_assignments.length === 0) {
          if (!isCancelled()) setState({ status: "no-access" });
          return;
        }
        const page = await api<Page<Condominium>>("/v1/condominiums/?is_active=true&page_size=200");
        const condos = page.results.filter((c) => roleFor(me, c.id));
        if (isCancelled()) return;
        if (!condos.length) {
          setState({ status: me.is_superuser ? "no-condo" : "no-access" });
          return;
        }
        let saved: number | null = null;
        try {
          saved = Number(localStorage.getItem(CONDO_KEY)) || null;
        } catch {}
        setCondoId((current) => (condos.some((c) => c.id === current) ? current : condos.some((c) => c.id === saved) ? saved : condos[0].id));
        setState({ status: "ready", me, condos });
      } catch (error) {
        if (!isCancelled()) setState({ status: "error", message: (error as Error).message });
      }
  }, []);

  useEffect(() => {
    if (!tokens.access()) {
      router.replace(`/login/?next=${encodeURIComponent(pathname)}`);
      return;
    }
    let cancelled = false;
    load(() => cancelled);
    return () => {
      cancelled = true;
    };
    // Load once per page load; navigation keeps the session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectCondo = useCallback((id: number) => {
    setCondoId(id);
    try {
      localStorage.setItem(CONDO_KEY, String(id));
    } catch {}
  }, []);

  const value = useMemo<Session | null>(() => {
    if (state.status !== "ready" || condoId === null) return null;
    const condo = state.condos.find((c) => c.id === condoId) ?? state.condos[0];
    const role = roleFor(state.me, condo.id) ?? "security";
    return { me: state.me, condos: state.condos, condo, role, isAdmin: role === "admin", selectCondo, reload: () => load(), logout };
  }, [state, condoId, selectCondo, load, logout]);

  if (state.status === "no-access") {
    return (
      <Centered>
        <h1 className="text-lg font-semibold">No dashboard access</h1>
        <p className="mt-2 text-sm text-muted">
          This dashboard is for condominium staff. Residents use the Elix mobile app.
        </p>
        <button className="mt-6 text-sm font-medium text-primary-700 hover:underline" onClick={logout}>
          Sign in with another account
        </button>
      </Centered>
    );
  }
  if (state.status === "no-condo") {
    return <Onboarding onCreated={(id) => { selectCondo(id); load(); }} onLogout={logout} />;
  }
  if (state.status === "error") {
    return (
      <Centered>
        <h1 className="text-lg font-semibold">Cannot reach the server</h1>
        <p className="mt-2 text-sm text-muted">{state.message}</p>
        <button className="mt-6 text-sm font-medium text-primary-700 hover:underline" onClick={() => location.reload()}>
          Try again
        </button>
      </Centered>
    );
  }
  if (!value) {
    return (
      <Centered>
        <div className="mx-auto h-6 w-6 animate-spin rounded-full border-2 border-line border-t-primary-600" />
      </Centered>
    );
  }
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="max-w-sm text-center">{children}</div>
    </div>
  );
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession outside SessionProvider");
  return session;
}
