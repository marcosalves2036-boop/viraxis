"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get("token");

  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("");
  const [countdown, setCountdown] = useState(5);

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("Token de verificação inválido ou ausente.");
      return;
    }

    api
      .verifyEmail(token)
      .then((res) => {
        setStatus("success");
        setMessage(res.message);
      })
      .catch((err: unknown) => {
        setStatus("error");
        setMessage(err instanceof Error ? err.message : "Erro ao verificar email.");
      });
  }, [token]);

  // Countdown redirect on success
  useEffect(() => {
    if (status !== "success") return;
    const interval = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          clearInterval(interval);
          router.push("/login");
        }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [status, router]);

  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative overflow-hidden">
      <div
        className="hero-glow w-[500px] h-[500px] bg-violet-700"
        style={{ top: "20%", left: "50%", transform: "translateX(-50%)" }}
      />

      <div className="relative z-10 w-full max-w-md">
        <div className="text-center mb-8">
          <Link href="/" className="text-2xl font-black gradient-text">
            VIRAXIS
          </Link>
        </div>

        <div className="card-glass rounded-2xl p-8 text-center">
          {status === "loading" && (
            <>
              <div className="text-5xl mb-4 animate-pulse">⏳</div>
              <h1 className="text-xl font-bold mb-3">Verificando seu email...</h1>
              <p className="text-white/40 text-sm">Aguarde um momento.</p>
            </>
          )}

          {status === "success" && (
            <>
              <div className="text-5xl mb-4">✅</div>
              <h1 className="text-xl font-bold mb-3">Email verificado!</h1>
              <p className="text-white/50 text-sm mb-6">{message}</p>
              <p className="text-white/30 text-xs mb-4">
                Redirecionando para o login em{" "}
                <span className="text-violet-400">{countdown}s</span>...
              </p>
              <Link
                href="/login"
                className="inline-block py-3 px-6 bg-violet-600 hover:bg-violet-500 text-white font-semibold rounded-xl transition-colors text-sm"
              >
                Ir para o login agora
              </Link>
            </>
          )}

          {status === "error" && (
            <>
              <div className="text-5xl mb-4">❌</div>
              <h1 className="text-xl font-bold mb-3">Falha na verificação</h1>
              <p className="text-white/50 text-sm mb-6">{message}</p>
              <p className="text-white/30 text-xs mb-4">
                O link pode ter expirado. Solicite um novo na página de cadastro.
              </p>
              <Link
                href="/cadastro"
                className="inline-block py-3 px-6 bg-violet-600 hover:bg-violet-500 text-white font-semibold rounded-xl transition-colors text-sm"
              >
                Voltar para cadastro
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-white/40">Carregando...</p>
      </div>
    }>
      <VerifyEmailContent />
    </Suspense>
  );
}
