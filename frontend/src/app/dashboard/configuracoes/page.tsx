"use client";

import { useEffect, useState } from "react";

interface User { id: string; email: string; full_name: string; }

export default function ConfiguracoesPage() {
  const [user, setUser] = useState<User | null>(null);
  const [tab, setTab] = useState<"perfil" | "senha" | "plano">("perfil");
  const [form, setForm] = useState({ full_name: "", email: "" });
  const [passwords, setPasswords] = useState({ current: "", new: "", confirm: "" });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  useEffect(() => {
    const raw = localStorage.getItem("viraxis_user");
    if (raw) {
      const u = JSON.parse(raw);
      setUser(u);
      setForm({ full_name: u.full_name, email: u.email });
    }
  }, []);

  async function savePerfil() {
    setSaving(true); setMsg(null);
    const token = localStorage.getItem("viraxis_token");
    try {
      const res = await fetch("/api/users/me", {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ full_name: form.full_name }),
      });
      if (res.ok) {
        const data = await res.json();
        localStorage.setItem("viraxis_user", JSON.stringify({ ...user, full_name: data.full_name }));
        setMsg({ type: "ok", text: "Perfil atualizado!" });
      } else {
        setMsg({ type: "err", text: "Erro ao atualizar." });
      }
    } catch {
      setMsg({ type: "err", text: "Erro de conexão." });
    } finally {
      setSaving(false);
    }
  }

  async function saveSenha() {
    if (passwords.new !== passwords.confirm) {
      setMsg({ type: "err", text: "Senhas não coincidem." }); return;
    }
    if (passwords.new.length < 8) {
      setMsg({ type: "err", text: "Senha deve ter ao menos 8 caracteres." }); return;
    }
    setSaving(true); setMsg(null);
    const token = localStorage.getItem("viraxis_token");
    try {
      const res = await fetch("/api/users/me/password", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ current_password: passwords.current, new_password: passwords.new }),
      });
      if (res.ok) {
        setMsg({ type: "ok", text: "Senha alterada com sucesso!" });
        setPasswords({ current: "", new: "", confirm: "" });
      } else {
        const data = await res.json();
        setMsg({ type: "err", text: data.detail ?? "Erro ao alterar senha." });
      }
    } catch {
      setMsg({ type: "err", text: "Erro de conexão." });
    } finally {
      setSaving(false);
    }
  }

  const TABS = [
    { id: "perfil", label: "Perfil" },
    { id: "senha", label: "Senha" },
    { id: "plano", label: "Plano" },
  ] as const;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Configurações</h1>
        <p className="text-white/40 text-sm mt-1">Gerencie sua conta VIRAXIS.</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 card-glass rounded-xl p-1">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => { setTab(t.id); setMsg(null); }}
            className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all
              ${tab === t.id ? "bg-violet-600 text-white" : "text-white/50 hover:text-white/80"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="card-glass rounded-2xl p-6 space-y-5">
        {/* Perfil */}
        {tab === "perfil" && (
          <>
            <h2 className="font-bold text-white">Informações do perfil</h2>
            <div className="flex items-center gap-4 pb-4 border-b" style={{ borderColor: "var(--border)" }}>
              <div className="w-16 h-16 rounded-full bg-violet-600/40 border-2 border-violet-500/40 flex items-center justify-center text-2xl font-black text-violet-300">
                {user?.full_name?.[0]?.toUpperCase() ?? "?"}
              </div>
              <div>
                <p className="font-semibold text-white">{user?.full_name}</p>
                <p className="text-white/40 text-sm">{user?.email}</p>
                <p className="text-xs text-violet-400 mt-1">Plano Free</p>
              </div>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-white/60 mb-1.5">Nome completo</label>
                <input
                  type="text"
                  value={form.full_name}
                  onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))}
                  className="w-full bg-white/[0.06] border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-violet-500/60 transition-colors"
                />
              </div>
              <div>
                <label className="block text-sm text-white/60 mb-1.5">Email</label>
                <input
                  type="email"
                  value={form.email}
                  disabled
                  className="w-full bg-white/[0.03] border border-white/10 rounded-xl px-4 py-3 text-sm text-white/40 cursor-not-allowed"
                />
                <p className="text-xs text-white/25 mt-1">Email não pode ser alterado.</p>
              </div>
            </div>
            {msg && (
              <div className={`rounded-xl px-4 py-3 text-sm border ${msg.type === "ok" ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300" : "bg-red-500/10 border-red-500/30 text-red-300"}`}>
                {msg.text}
              </div>
            )}
            <button
              onClick={savePerfil}
              disabled={saving}
              className="w-full py-3 bg-violet-600 hover:bg-violet-500 disabled:bg-violet-800 text-white text-sm font-semibold rounded-xl transition-colors"
            >
              {saving ? "Salvando..." : "Salvar alterações"}
            </button>
          </>
        )}

        {/* Senha */}
        {tab === "senha" && (
          <>
            <h2 className="font-bold text-white">Alterar senha</h2>
            <div className="space-y-4">
              {[
                { label: "Senha atual", key: "current" },
                { label: "Nova senha", key: "new" },
                { label: "Confirmar nova senha", key: "confirm" },
              ].map(({ label, key }) => (
                <div key={key}>
                  <label className="block text-sm text-white/60 mb-1.5">{label}</label>
                  <input
                    type="password"
                    value={passwords[key as keyof typeof passwords]}
                    onChange={e => setPasswords(p => ({ ...p, [key]: e.target.value }))}
                    placeholder="••••••••"
                    className="w-full bg-white/[0.06] border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none focus:border-violet-500/60 transition-colors"
                  />
                </div>
              ))}
            </div>
            {msg && (
              <div className={`rounded-xl px-4 py-3 text-sm border ${msg.type === "ok" ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300" : "bg-red-500/10 border-red-500/30 text-red-300"}`}>
                {msg.text}
              </div>
            )}
            <button
              onClick={saveSenha}
              disabled={saving || !passwords.current || !passwords.new}
              className="w-full py-3 bg-violet-600 hover:bg-violet-500 disabled:bg-violet-800 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-xl transition-colors"
            >
              {saving ? "Alterando..." : "Alterar senha"}
            </button>
          </>
        )}

        {/* Plano */}
        {tab === "plano" && (
          <>
            <h2 className="font-bold text-white">Seu plano atual</h2>
            <div className="rounded-xl p-4 bg-violet-600/10 border border-violet-500/30">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-bold text-violet-300 text-lg">Free</p>
                  <p className="text-white/40 text-sm mt-0.5">Plano gratuito</p>
                </div>
                <span className="text-2xl">🆓</span>
              </div>
              <ul className="mt-4 space-y-2 text-sm text-white/60">
                <li className="flex gap-2"><span className="text-emerald-400">✓</span> 1 escritório viral</li>
                <li className="flex gap-2"><span className="text-emerald-400">✓</span> Agente BRAIN básico</li>
                <li className="flex gap-2"><span className="text-white/25">✗</span> Scout de tendências</li>
                <li className="flex gap-2"><span className="text-white/25">✗</span> Publicação automática</li>
                <li className="flex gap-2"><span className="text-white/25">✗</span> Analíticos avançados</li>
              </ul>
            </div>

            <div className="space-y-3">
              {[
                { plan: "Pro", price: "R$97/mês", offices: "5 escritórios", highlight: true },
                { plan: "Business", price: "R$297/mês", offices: "Escritórios ilimitados", highlight: false },
              ].map(p => (
                <div key={p.plan} className={`rounded-xl p-4 border ${p.highlight ? "bg-violet-600/10 border-violet-500/30" : "bg-white/[0.04] border-white/10"}`}>
                  <div className="flex items-center justify-between mb-2">
                    <p className={`font-bold ${p.highlight ? "text-violet-300" : "text-white"}`}>{p.plan}</p>
                    <p className="text-white font-bold">{p.price}</p>
                  </div>
                  <p className="text-white/40 text-sm mb-3">{p.offices} + todas as features</p>
                  <button className={`w-full py-2 rounded-lg text-sm font-semibold transition-colors
                    ${p.highlight ? "bg-violet-600 hover:bg-violet-500 text-white" : "bg-white/[0.08] hover:bg-white/[0.12] text-white/70"}`}>
                    Em breve
                  </button>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
