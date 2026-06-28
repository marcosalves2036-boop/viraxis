"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { auth } from "@/lib/api";

interface User {
  id: string;
  email: string;
  full_name: string;
  plan?: string;
  role?: string;
}

const NAV = [
  { href: "/dashboard", label: "Visão Geral", icon: "⊞", exact: true },
  { href: "/dashboard/escritorios", label: "Escritórios", icon: "🏢", exact: false },
  { href: "/dashboard/conteudo", label: "Conteúdo", icon: "📹", exact: false },
  { href: "/dashboard/canais", label: "Canais", icon: "📡", exact: false },
  { href: "/dashboard/analiticos", label: "Analíticos", icon: "📊", exact: false },
  { href: "/dashboard/biblioteca", label: "Biblioteca", icon: "🎬", exact: false },
  { href: "/dashboard/configuracoes", label: "Configurações", icon: "⚙️", exact: false },
];

const NAV_ADMIN = [
  { href: "/dashboard/dev", label: "Dev — Kevin & Davi", icon: "🤖", exact: false },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    const token = auth.getToken();
    if (!token) { router.replace("/login"); return; }
    const raw = localStorage.getItem("viraxis_user");
    if (raw) {
      try { setUser(JSON.parse(raw)); } catch {}
    }
    // Refresh from API — picks up role + latest plan
    fetch("/api/users/me", { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d) {
          setUser(d);
          localStorage.setItem("viraxis_user", JSON.stringify(d));
        }
      })
      .catch(() => {});
  }, [router]);

  function handleLogout() {
    auth.clear();
    router.replace("/login");
  }

  const isAdmin = user?.role === "admin";
  const initials = user?.full_name?.split(" ").map(n => n[0]).slice(0, 2).join("").toUpperCase() ?? "?";

  return (
    <div className="min-h-screen flex" style={{ background: "var(--background)" }}>
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/60 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed md:static z-30 inset-y-0 left-0 w-60 flex flex-col border-r transition-transform duration-200
          ${sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}`}
        style={{ borderColor: "var(--border)", background: "rgba(6,7,10,0.98)" }}
      >
        {/* Logo */}
        <div className="px-5 py-5 border-b" style={{ borderColor: "var(--border)" }}>
          <Link href="/dashboard" className="text-xl font-black gradient-text">VIRAXIS</Link>
          <p className="text-white/30 text-xs mt-0.5">Painel de controle</p>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {NAV.map(({ href, label, icon, exact }) => {
            const active = exact ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                onClick={() => setSidebarOpen(false)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all
                  ${active
                    ? "bg-violet-600/20 text-violet-300 border border-violet-500/30"
                    : "text-white/50 hover:text-white/80 hover:bg-white/[0.04]"
                  }`}
              >
                <span className="text-base">{icon}</span>
                {label}
              </Link>
            );
          })}

          {/* Admin-only section */}
          {isAdmin && (
            <>
              <div className="my-2 border-t" style={{ borderColor: "var(--border)" }} />
              <p className="px-3 pt-1 pb-0.5 text-[10px] font-semibold text-white/20 uppercase tracking-widest">
                Admin
              </p>
              {NAV_ADMIN.map(({ href, label, icon, exact }) => {
                const active = exact ? pathname === href : pathname.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setSidebarOpen(false)}
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all
                      ${active
                        ? "bg-cyan-600/20 text-cyan-300 border border-cyan-500/30"
                        : "text-white/40 hover:text-white/70 hover:bg-white/[0.04]"
                      }`}
                  >
                    <span className="text-base">{icon}</span>
                    {label}
                  </Link>
                );
              })}
            </>
          )}
        </nav>

        {/* User */}
        <div className="px-3 py-4 border-t" style={{ borderColor: "var(--border)" }}>
          <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-white/[0.04]">
            <div className="w-8 h-8 rounded-full bg-violet-600/40 border border-violet-500/40 flex items-center justify-center text-xs font-bold text-violet-300 shrink-0">
              {initials}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <p className="text-sm font-medium text-white truncate">{user?.full_name ?? "..."}</p>
                {isAdmin && (
                  <span className="text-[9px] font-bold px-1 py-0.5 rounded bg-amber-500/20 text-amber-400 border border-amber-500/30 shrink-0">
                    ADM
                  </span>
                )}
              </div>
              <p className="text-xs text-white/30 truncate">{user?.email ?? ""}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="w-full mt-2 py-2 text-xs text-white/30 hover:text-white/60 transition-colors rounded-xl hover:bg-white/[0.04]"
          >
            Sair da conta
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="flex items-center justify-between px-6 py-4 border-b shrink-0" style={{ borderColor: "var(--border)" }}>
          <button
            className="md:hidden text-white/40 hover:text-white/80 text-xl"
            onClick={() => setSidebarOpen(true)}
          >
            ☰
          </button>
          <div className="hidden md:block" />
          <div className="flex items-center gap-3">
            <span className="text-xs text-white/30 hidden sm:block">
              Plano <span className="text-violet-400 font-semibold capitalize">{user?.plan ?? "Free"}</span>
            </span>
            <Link
              href="/dashboard/configuracoes"
              className="text-xs px-3 py-1.5 rounded-lg bg-violet-600/20 border border-violet-500/30 text-violet-300 hover:bg-violet-600/30 transition-colors"
            >
              Upgrade →
            </Link>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
