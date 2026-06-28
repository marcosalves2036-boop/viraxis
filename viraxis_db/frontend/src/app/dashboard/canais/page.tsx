"use client";

import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

const BACKEND = process.env.NEXT_PUBLIC_API_URL || "https://viraxis.onrender.com";

interface Office {
  id: string;
  name: string;
}

interface SocialAccount {
  id: string;
  platform: string;
  platform_username: string;
  platform_user_id: string | null;
  office_id: string | null;
  is_active: boolean;
  token_expires_at: string | null;
  created_at: string;
}

const PLATFORM_LABELS: Record<string, string> = {
  youtube: "YouTube",
  tiktok: "TikTok",
  facebook: "Facebook / Instagram",
  instagram: "Instagram",
  kwai: "Kwai",
};

const PLATFORM_ICONS: Record<string, string> = {
  youtube: "▶️",
  tiktok: "🎵",
  facebook: "📘",
  instagram: "📸",
  kwai: "🎬",
};

const PLATFORM_COLORS: Record<string, string> = {
  youtube: "red",
  tiktok: "pink",
  facebook: "blue",
  instagram: "purple",
  kwai: "orange",
};

const COLOR_CLASSES: Record<string, { bg: string; border: string; text: string; btn: string }> = {
  red:    { bg: "bg-red-500/10",    border: "border-red-500/30",    text: "text-red-300",    btn: "bg-red-600 hover:bg-red-500" },
  pink:   { bg: "bg-pink-500/10",   border: "border-pink-500/30",   text: "text-pink-300",   btn: "bg-pink-600 hover:bg-pink-500" },
  blue:   { bg: "bg-blue-500/10",   border: "border-blue-500/30",   text: "text-blue-300",   btn: "bg-blue-600 hover:bg-blue-500" },
  purple: { bg: "bg-violet-500/10", border: "border-violet-500/30", text: "text-violet-300", btn: "bg-violet-600 hover:bg-violet-500" },
  orange: { bg: "bg-orange-500/10", border: "border-orange-500/30", text: "text-orange-300", btn: "bg-orange-600 hover:bg-orange-500" },
};

const CONNECT_PLATFORMS = [
  { key: "google",   label: "YouTube",               icon: "▶️", color: "red"   },
  { key: "tiktok",  label: "TikTok",                 icon: "🎵", color: "pink"  },
  { key: "meta",    label: "Instagram",                icon: "📸", color: "purple"},
];

function CanaisContent() {
  const searchParams = useSearchParams();
  const defaultOffice = searchParams.get("office_id") ?? "";

  const [offices, setOffices] = useState<Office[]>([]);
  const [selectedOffice, setSelectedOffice] = useState(defaultOffice);
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [loading, setLoading] = useState(false);
  const [disconnecting, setDisconnecting] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  // Load offices
  useEffect(() => {
    const token = localStorage.getItem("viraxis_token");
    if (!token) return;
    fetch("/api/offices", { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then((data: Office[]) => {
        setOffices(data);
        if (!selectedOffice && data.length > 0) setSelectedOffice(data[0].id);
      })
      .catch(() => {});
  }, []);

  // Load accounts for selected office
  const loadAccounts = useCallback(async () => {
    if (!selectedOffice) return;
    setLoading(true);
    const token = localStorage.getItem("viraxis_token");
    try {
      const res = await fetch(`/api/social-accounts?office_id=${selectedOffice}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setAccounts(await res.json());
    } catch {}
    finally { setLoading(false); }
  }, [selectedOffice]);

  useEffect(() => { loadAccounts(); }, [loadAccounts]);

  function connectPlatform(platformKey: string) {
    const token = localStorage.getItem("viraxis_token");
    if (!token) return;
    const url = `${BACKEND}/auth/${platformKey}/connect?access_token=${token}${selectedOffice ? `&office_id=${selectedOffice}` : ""}`;
    window.location.href = url;
  }

  async function disconnect(accountId: string) {
    if (!confirm("Desconectar esta conta?")) return;
    setDisconnecting(accountId);
    setMsg(null);
    const token = localStorage.getItem("viraxis_token");
    try {
      const res = await fetch(`/api/social-accounts/${accountId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok || res.status === 204) {
        setMsg({ type: "ok", text: "Conta desconectada." });
        setAccounts(prev => prev.filter(a => a.id !== accountId));
      } else {
        const d = await res.json().catch(() => ({}));
        setMsg({ type: "err", text: d.detail ?? "Erro ao desconectar." });
      }
    } catch {
      setMsg({ type: "err", text: "Erro de conexão." });
    } finally {
      setDisconnecting(null);
    }
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
  }

  // Map accounts by platform for quick lookup
  const accountsByPlatform: Record<string, SocialAccount> = {};
  for (const acc of accounts) {
    // youtube, tiktok, facebook/instagram
    const key = acc.platform === "youtube" ? "youtube" : acc.platform === "tiktok" ? "tiktok" : acc.platform === "facebook" ? "facebook" : acc.platform;
    if (!accountsByPlatform[key]) accountsByPlatform[key] = acc;
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Canais Sociais</h1>
        <p className="text-white/40 text-sm mt-1">Vincule suas contas para publicar conteúdo automaticamente.</p>
      </div>

      {/* Office selector */}
      {offices.length > 1 && (
        <div className="card-glass rounded-xl p-4">
          <label className="block text-xs text-white/40 mb-2 uppercase tracking-wider">Escritório</label>
          <select
            value={selectedOffice}
            onChange={e => setSelectedOffice(e.target.value)}
            className="w-full bg-white/[0.06] border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-violet-500/60 transition-colors"
          >
            {offices.map(o => (
              <option key={o.id} value={o.id} style={{ background: "#0a0b0f" }}>{o.name}</option>
            ))}
          </select>
        </div>
      )}

      {/* Feedback */}
      {msg && (
        <div className={`rounded-xl px-4 py-3 text-sm border ${msg.type === "ok" ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300" : "bg-red-500/10 border-red-500/30 text-red-300"}`}>
          {msg.text}
        </div>
      )}

      {/* Platform cards */}
      <div className="space-y-3">
        {CONNECT_PLATFORMS.map(({ key, label, icon, color }) => {
          const platformKey = key === "google" ? "youtube" : key === "meta" ? "facebook" : key;
          const acc = accountsByPlatform[platformKey];
          const c = COLOR_CLASSES[color];

          return (
            <div key={key} className={`rounded-2xl p-5 border ${c.bg} ${c.border}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{icon}</span>
                  <div>
                    <p className={`font-bold ${c.text}`}>{label}</p>
                    {acc ? (
                      <p className="text-white/50 text-sm mt-0.5">
                        @{acc.platform_username} · desde {formatDate(acc.created_at)}
                      </p>
                    ) : (
                      <p className="text-white/30 text-sm mt-0.5">Não conectado</p>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {acc ? (
                    <>
                      <span className="text-xs px-2 py-1 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-400">
                        ✓ Ativo
                      </span>
                      <button
                        onClick={() => disconnect(acc.id)}
                        disabled={disconnecting === acc.id}
                        className="text-xs px-3 py-1.5 rounded-lg bg-white/[0.06] border border-white/10 text-white/50 hover:text-white/80 hover:bg-white/[0.10] transition-colors disabled:opacity-40"
                      >
                        {disconnecting === acc.id ? "..." : "Desconectar"}
                      </button>
                      <button
                        onClick={() => connectPlatform(key)}
                        className={`text-xs px-3 py-1.5 rounded-lg ${c.btn} text-white font-semibold transition-colors`}
                      >
                        Reconectar
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => connectPlatform(key)}
                      disabled={!selectedOffice}
                      className={`px-4 py-2 rounded-xl ${c.btn} text-white text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed`}
                    >
                      Conectar
                    </button>
                  )}
                </div>
              </div>

              {acc?.token_expires_at && new Date(acc.token_expires_at) < new Date() && (
                <div className="mt-3 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
                  ⚠️ Token expirado — reconecte para continuar publicando.
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Raw accounts list (extra accounts) */}
      {accounts.filter(a => !["youtube","tiktok","facebook","instagram"].includes(a.platform)).length > 0 && (
        <div className="card-glass rounded-2xl p-5 space-y-3">
          <h2 className="text-sm font-semibold text-white/60 uppercase tracking-wider">Outras contas</h2>
          {accounts
            .filter(a => !["youtube","tiktok","facebook","instagram"].includes(a.platform))
            .map(acc => (
              <div key={acc.id} className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
                <div className="flex items-center gap-3">
                  <span className="text-lg">{PLATFORM_ICONS[acc.platform] ?? "🔗"}</span>
                  <div>
                    <p className="text-sm text-white font-medium">{PLATFORM_LABELS[acc.platform] ?? acc.platform}</p>
                    <p className="text-xs text-white/40">@{acc.platform_username}</p>
                  </div>
                </div>
                <button
                  onClick={() => disconnect(acc.id)}
                  disabled={disconnecting === acc.id}
                  className="text-xs px-3 py-1.5 rounded-lg bg-white/[0.06] border border-white/10 text-white/50 hover:text-red-400 hover:border-red-500/30 transition-colors"
                >
                  {disconnecting === acc.id ? "..." : "Desconectar"}
                </button>
              </div>
            ))}
        </div>
      )}

      {loading && (
        <div className="text-center py-8 text-white/30 text-sm">Carregando contas...</div>
      )}

      {!loading && !selectedOffice && (
        <div className="text-center py-8 text-white/30 text-sm">
          Selecione um escritório para gerenciar os canais.
        </div>
      )}
    </div>
  );
}

export default function CanaisPage() {
  return (
    <Suspense fallback={
      <div className="text-white/30 text-sm p-6">Carregando...</div>
    }>
      <CanaisContent />
    </Suspense>
  );
}
