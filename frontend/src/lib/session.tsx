"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { api, LOGOUT_EVENT, logout as clearTokens, tokens } from "./api";
import type { Condominium, Me, Page, Role } from "./types";

type Session = {
  me: Me;
  condos: Condominium[];
  condo: Condominium;
  role: Role;
  isAdmin: boolean;
  selectCondo: (id: number) => void;
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

  useEffect(() => {
    if (!tokens.access()) {
      router.replace(`/login/?next=${encodeURIComponent(pathname)}`);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const me = await api<Me>("/v1/auth/me/");
        if (!me.is_superuser && me.staff_assignments.length === 0) {
          if (!cancelled) setState({ status: "no-access" });
          return;
        }
        const page = await api<Page<Condominium>>("/v1/condominiums/?is_active=true&page_size=200");
        const condos = page.results.filter((c) => roleFor(me, c.id));
        if (cancelled) return;
        if (!condos.length) {
          setState({ status: "no-access" });
          return;
        }
        let saved: number | null = null;
        try {
          saved = Number(localStorage.getItem(CONDO_KEY)) || null;
        } catch {}
        setCondoId(condos.some((c) => c.id === saved) ? saved : condos[0].id);
        setState({ status: "ready", me, condos });
      } catch (error) {
        if (!cancelled) setState({ status: "error", message: (error as Error).message });
      }
    })();
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
    return { me: state.me, condos: state.condos, condo, role, isAdmin: role === "admin", selectCondo, logout };
  }, [state, condoId, selectCondo, logout]);

  if (state.status === "no-access") {
    return (
      <Centered>
        <h1 className="text-lg font-semibold">No dashboard access</h1>
        <p className="mt-2 text-sm text-slate-500">
          This dashboard is for condominium staff. Residents use the Elix mobile app.
        </p>
        <button className="mt-6 text-sm font-medium text-teal-700 hover:underline" onClick={logout}>
          Sign in with another account
        </button>
      </Centered>
    );
  }
  if (state.status === "error") {
    return (
      <Centered>
        <h1 className="text-lg font-semibold">Cannot reach the server</h1>
        <p className="mt-2 text-sm text-slate-500">{state.message}</p>
        <button className="mt-6 text-sm font-medium text-teal-700 hover:underline" onClick={() => location.reload()}>
          Try again
        </button>
      </Centered>
    );
  }
  if (!value) {
    return (
      <Centered>
        <div className="mx-auto h-6 w-6 animate-spin rounded-full border-2 border-slate-300 border-t-teal-600" />
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
