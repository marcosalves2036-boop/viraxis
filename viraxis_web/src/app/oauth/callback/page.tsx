"use client";

import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Suspense } from "react";

const PLATFORM_LABELS: Record<string, string> = {
  youtube: "YouTube",
  tiktok: "TikTok",
  facebook: "Facebook / Instagram",
};

const PLATFORM_ICONS: Record<string, string> = {
  youtube: "▶️",
  tiktok: "🎵",
  facebook: "📘",
};

function CallbackContent() {
  const params = useSearchParams();
  const router = useRouter();
  const [countdown, setCountdown] = useState(4);

  const platform = params.get("platform") ?? "";
  const status = params.get("status") ?? "";
  const message = params.get("message") ?? "";
  const officeId = params.get("office_id") ?? "";

  const success = status === "success";
  const label = PLATFORM_LABELS[platform] ?? platform;
  const icon = PLATFORM_ICONS[platform] ?? "🔗";

  useEffect(() => {
    const dest = officeId
      ? `/dashboard/canais?office_id=${officeId}`
      : "/dashboard/canais";

    const interval = setInterval(() => {
      setCountdown(c => {
        if (c <= 1) {
          clearInterval(interval);
          router.replace(dest);
        }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [router, officeId]);

  return (
    <div className="min-h-screen flex items-center justify-center p-6"
      style={{ background: "var(--background)" }}>
      <div className="card-glass rounded-2xl p-10 max-w-md w-full text-center space-y-6">
        <div className="text-5xl">{success ? "✅" : "❌"}</div>

        <div>
          <h1 className="text-xl font-black text-white">
            {success
              ? `${icon} ${label} conectado!`
              : `Falha ao conectar ${label}`}
          </h1>
          {message && (
            <p className="text-white/40 text-sm mt-2">{message}</p>
          )}
        </div>

        <div className={`rounded-xl px-4 py-3 text-sm border ${
          success
            ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
            : "bg-red-500/10 border-red-500/30 text-red-300"
        }`}>
          {success
            ? "Conta vinculada com sucesso. Você já pode publicar conteúdo nesta plataforma."
            : "Não foi possível concluir a autorização. Tente novamente."}
        </div>

        <p className="text-white/30 text-xs">
          Redirecionando em {countdown}s...
        </p>
      </div>
    </div>
  );
}

export default function OAuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center"
        style={{ background: "var(--background)" }}>
        <div className="text-white/40 text-sm">Processando...</div>
      </div>
    }>
      <CallbackContent />
    </Suspense>
  );
}
