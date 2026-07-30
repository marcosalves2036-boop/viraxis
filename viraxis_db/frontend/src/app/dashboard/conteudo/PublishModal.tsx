"use client";

import { useEffect, useMemo, useState } from "react";

export type Platform = "tiktok" | "instagram" | "youtube";

const PLATFORMS: { id: Platform; label: string; icon: string }[] = [
  { id: "tiktok", label: "TikTok", icon: "🎵" },
  { id: "instagram", label: "Instagram", icon: "📸" },
  { id: "youtube", label: "YouTube", icon: "▶️" },
];

// Limites conhecidos de legenda por plataforma (caracteres).
const CAPTION_LIMITS: Record<Platform, number> = {
  tiktok: 2200,
  instagram: 2200,
  youtube: 5000,
};

interface SocialAccount {
  id: string;
  platform: string;
  platform_username: string;
  office_id: string | null;
  is_active: boolean;
}

interface PublishResponse {
  content_item_id: string;
  successful_platforms: string[];
  failed_platforms: string[];
  message: string;
}

// Subconjunto de ProductionMeta relevante para sugerir uma legenda default.
// Tipado à parte para não acoplar este componente ao shape completo usado nas páginas.
export interface PublishProductionMeta {
  roteiro?: { hook?: string; cta?: string };
  seo?: { descricao?: string; hashtags?: string[] };
}

interface PublishModalProps {
  itemId: string;
  officeId: string;
  itemTitle: string;
  productionMeta?: PublishProductionMeta;
  onClose: () => void;
  onPublished: (newStatus: string) => void;
}

function buildDefaultCaption(title: string, meta?: PublishProductionMeta): string {
  if (meta?.seo?.descricao) {
    const hashtags = (meta.seo.hashtags ?? [])
      .filter(Boolean)
      .map(h => (h.startsWith("#") ? h : `#${h}`))
      .join(" ");
    return hashtags ? `${meta.seo.descricao}\n\n${hashtags}` : meta.seo.descricao;
  }
  if (meta?.roteiro?.hook) {
    const cta = meta.roteiro.cta ? `\n\n${meta.roteiro.cta}` : "";
    return `${meta.roteiro.hook}${cta}`;
  }
  return title;
}

export function PublishModal({ itemId, officeId, itemTitle, productionMeta, onClose, onPublished }: PublishModalProps) {
  const [selected, setSelected] = useState<Platform | null>(null);
  const [accountsByPlatform, setAccountsByPlatform] = useState<Record<string, SocialAccount[]>>({});
  const [loadingAccounts, setLoadingAccounts] = useState(true);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [caption, setCaption] = useState(() => buildDefaultCaption(itemTitle, productionMeta));
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadAccounts() {
      setLoadingAccounts(true);
      try {
        const token = typeof window !== "undefined" ? localStorage.getItem("viraxis_token") : null;
        const r = await fetch(`/api/social-accounts?office_id=${officeId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (r.ok) {
          const accounts: SocialAccount[] = await r.json();
          const grouped: Record<string, SocialAccount[]> = {};
          for (const acc of accounts) {
            if (!acc.is_active) continue;
            (grouped[acc.platform] ??= []).push(acc);
          }
          if (!cancelled) setAccountsByPlatform(grouped);
        }
      } catch {
        // silencioso — trata como "nenhuma conta conectada" abaixo
      } finally {
        if (!cancelled) setLoadingAccounts(false);
      }
    }
    loadAccounts();
    return () => { cancelled = true; };
  }, [officeId]);

  // Sempre que a plataforma selecionada mudar (ou as contas terminarem de carregar),
  // seleciona a primeira conta disponível por padrão.
  useEffect(() => {
    if (!selected) {
      setSelectedAccountId(null);
      return;
    }
    const accounts = accountsByPlatform[selected] ?? [];
    setSelectedAccountId(accounts[0]?.id ?? null);
  }, [selected, accountsByPlatform]);

  const selectedAccounts = selected ? accountsByPlatform[selected] ?? [] : [];
  const selectedHasAccount = selectedAccounts.length > 0;
  const showAccountPicker = selectedAccounts.length > 1;

  const captionLimit = selected ? CAPTION_LIMITS[selected] : null;
  const captionLength = caption.length;
  const captionOverLimit = captionLimit != null && captionLength > captionLimit;

  const errorFromLimit = useMemo(() => {
    if (captionOverLimit && captionLimit != null && selected) {
      const platformLabel = PLATFORMS.find(p => p.id === selected)?.label ?? selected;
      return `A legenda excede o limite de ${captionLimit} caracteres do ${platformLabel}.`;
    }
    return null;
  }, [captionOverLimit, captionLimit, selected]);

  async function handleConfirm() {
    if (!selected || publishing) return;
    if (!selectedAccountId) {
      setError(`Conecte sua conta do ${selected} antes de publicar.`);
      return;
    }
    if (captionOverLimit) {
      setError(errorFromLimit);
      return;
    }
    setPublishing(true);
    setError(null);
    try {
      const trimmedCaption = caption.trim();
      const r = await fetch(`/api/offices/${officeId}/content-items/${itemId}/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          targets: [
            {
              platform: selected,
              social_account_id: selectedAccountId,
              caption: trimmedCaption.length > 0 ? trimmedCaption : null,
              hashtags: [],
            },
          ],
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        if (r.status === 404) {
          throw new Error("Conteúdo ou escritório não encontrado.");
        }
        if (r.status === 422) {
          throw new Error(body.detail ?? "Este conteúdo ainda não está pronto para ser publicado.");
        }
        throw new Error(body.detail ?? "Erro ao publicar. Tente novamente.");
      }
      const result = body as PublishResponse;
      if (result.failed_platforms?.includes(selected)) {
        throw new Error(result.message || `Falha ao publicar no ${selected}.`);
      }
      setSuccess(true);
      onPublished("published");
      setTimeout(onClose, 1500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao publicar. Tente novamente.");
    } finally {
      setPublishing(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-sm rounded-2xl border p-6 max-h-[90vh] overflow-y-auto"
        style={{ background: "rgba(8,9,16,0.99)", borderColor: "rgba(255,255,255,0.08)" }}
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="min-w-0">
            <h3 className="text-white font-bold text-sm">📤 Publicar conteúdo</h3>
            <p className="text-white/40 text-xs mt-1 line-clamp-1">{itemTitle}</p>
          </div>
          <button onClick={onClose} className="text-white/30 hover:text-white/60 text-lg shrink-0">✕</button>
        </div>

        {success ? (
          <div className="py-6 text-center">
            <p className="text-emerald-400 text-2xl mb-2">✅</p>
            <p className="text-emerald-300 text-sm font-semibold">Publicado com sucesso!</p>
          </div>
        ) : (
          <>
            <p className="text-white/40 text-xs font-semibold uppercase tracking-wider mb-2">Escolha a plataforma</p>
            <div className="grid grid-cols-3 gap-2 mb-3">
              {PLATFORMS.map(p => {
                const connected = (accountsByPlatform[p.id]?.length ?? 0) > 0;
                return (
                  <button
                    key={p.id}
                    onClick={() => setSelected(p.id)}
                    disabled={publishing || loadingAccounts}
                    className={`relative flex flex-col items-center gap-1.5 py-3 rounded-xl border text-xs font-medium transition-colors disabled:opacity-50 ${
                      selected === p.id
                        ? "bg-violet-600/30 border-violet-500/50 text-violet-200"
                        : "bg-white/[0.04] border-white/10 text-white/50 hover:border-white/20"
                    }`}
                  >
                    <span className="text-xl">{p.icon}</span>
                    {p.label}
                    {!loadingAccounts && !connected && (
                      <span className="absolute -top-1.5 -right-1.5 text-[9px] px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30">
                        !
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {loadingAccounts && (
              <p className="text-white/30 text-xs mb-4 animate-pulse">Verificando contas conectadas…</p>
            )}

            {!loadingAccounts && selected && !selectedHasAccount && (
              <div className="mb-4 p-3 rounded-xl border border-amber-500/20 bg-amber-500/5">
                <p className="text-amber-400 text-xs leading-relaxed">
                  ⚠️ Nenhuma conta do {PLATFORMS.find(p => p.id === selected)?.label} conectada a este escritório.
                </p>
                <a
                  href={`/dashboard/canais?office_id=${officeId}`}
                  className="mt-2 inline-block text-xs text-violet-400 hover:text-violet-300 hover:underline"
                >
                  Conectar conta agora →
                </a>
              </div>
            )}

            {!loadingAccounts && showAccountPicker && (
              <div className="mb-4">
                <p className="text-white/40 text-xs font-semibold uppercase tracking-wider mb-2">
                  Qual conta do {PLATFORMS.find(p => p.id === selected)?.label}?
                </p>
                <div className="flex flex-col gap-1.5">
                  {selectedAccounts.map(acc => (
                    <label
                      key={acc.id}
                      className={`flex items-center gap-2 py-2 px-3 rounded-xl border text-xs cursor-pointer transition-colors ${
                        selectedAccountId === acc.id
                          ? "bg-violet-600/20 border-violet-500/50 text-violet-200"
                          : "bg-white/[0.04] border-white/10 text-white/60 hover:border-white/20"
                      }`}
                    >
                      <input
                        type="radio"
                        name="publish-account"
                        value={acc.id}
                        checked={selectedAccountId === acc.id}
                        onChange={() => setSelectedAccountId(acc.id)}
                        disabled={publishing}
                        className="accent-violet-500"
                      />
                      <span className="truncate">@{acc.platform_username}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {!loadingAccounts && selected && selectedHasAccount && (
              <div className="mb-4">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-white/40 text-xs font-semibold uppercase tracking-wider">Legenda / hashtags</p>
                  {captionLimit != null && (
                    <span className={`text-[10px] font-medium ${captionOverLimit ? "text-red-400" : "text-white/30"}`}>
                      {captionLength}/{captionLimit}
                    </span>
                  )}
                </div>
                <textarea
                  value={caption}
                  onChange={e => setCaption(e.target.value)}
                  disabled={publishing}
                  rows={4}
                  placeholder="Escreva a legenda e hashtags para este post…"
                  className={`w-full resize-none rounded-xl border bg-white/[0.04] px-3 py-2 text-xs text-white/80 placeholder:text-white/25 outline-none transition-colors focus:border-violet-500/50 disabled:opacity-50 ${
                    captionOverLimit ? "border-red-500/50" : "border-white/10"
                  }`}
                />
                {captionOverLimit && (
                  <p className="text-red-400 text-[10px] mt-1">{errorFromLimit}</p>
                )}
              </div>
            )}

            {error && (
              <div className="mb-4 p-3 rounded-xl border border-red-500/20 bg-red-500/5">
                <p className="text-red-400 text-xs leading-relaxed">❌ {error}</p>
              </div>
            )}

            <button
              onClick={handleConfirm}
              disabled={!selected || !selectedHasAccount || !selectedAccountId || captionOverLimit || publishing || loadingAccounts}
              className="w-full py-2.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-bold rounded-xl transition-colors"
            >
              {publishing ? "⚙️ Publicando…" : "Confirmar publicação"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
