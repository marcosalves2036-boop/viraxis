"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { auth } from "@/lib/api";

interface DevSession {
  id: string;
  task: string;
  status: "pending" | "running" | "done" | "error";
  started_at: string | null;
  finished_at: string | null;
  kevin_spec: string;
  davi_output: string;
  review_output: string;
  error: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  running: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  done: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  error: "bg-red-500/15 text-red-400 border-red-500/30",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "⏳ Aguardando",
  running: "⚙️ Executando",
  done: "✅ Concluído",
  error: "❌ Erro",
};

const EXAMPLES = [
  "Adicionar endpoint PATCH /offices/{id}/status para pausar ou ativar um escritório",
  "Criar router de social_accounts com endpoints CRUD básicos",
  "Adicionar campo 'description' ao model Office e ao endpoint de criação",
  "Criar endpoint GET /offices/{id}/stats com métricas de conteúdo do escritório",
];

export default function DevPage() {
  const router = useRouter();
  const [authorized, setAuthorized] = useState<boolean | null>(null);
  const [task, setTask] = useState("");
  const [session, setSession] = useState<DevSession | null>(null);
  const [sessions, setSessions] = useState<DevSession[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"kevin" | "davi" | "review">("kevin");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Admin guard
  useEffect(() => {
    const token = auth.getToken();
    if (!token) { router.replace("/login"); return; }
    fetch("/api/users/me", { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d || d.role !== "admin") {
          router.replace("/dashboard");
        } else {
          setAuthorized(true);
        }
      })
      .catch(() => router.replace("/dashboard"));
  }, [router]);

  const token = typeof window !== "undefined" ? localStorage.getItem("viraxis_token") : null;
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };

  useEffect(() => {
    if (authorized) loadSessions();
  }, [authorized]);

  async function loadSessions() {
    try {
      const r = await fetch("/api/dev/sessions", { headers });
      if (r.ok) setSessions(await r.json());
    } catch {}
  }

  function startPolling(sessionId: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const r = await fetch(`/api/dev/task/${sessionId}`, { headers });
        if (r.ok) {
          const data: DevSession = await r.json();
          setSession(data);
          if (data.status === "done" || data.status === "error") {
            clearInterval(pollRef.current!);
            loadSessions();
          }
        }
      } catch {}
    }, 2500);
  }

  async function runTask() {
    if (!task.trim() || loading) return;
    setLoading(true);
    setSession(null);
    try {
      const r = await fetch("/api/dev/task", {
        method: "POST",
        headers,
        body: JSON.stringify({ task }),
      });
      if (r.ok) {
        const data: DevSession = await r.json();
        setSession(data);
        startPolling(data.id);
      } else {
        const err = await r.json();
        alert(`Erro: ${err.detail}`);
      }
    } catch (e) {
      alert(`Erro de conexão: ${e}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  // Loading / unauthorized states
  if (authorized === null) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-white/30 text-sm animate-pulse">Verificando permissões...</div>
      </div>
    );
  }

  const isRunning = session?.status === "running" || session?.status === "pending";

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-1">
          <h1 className="text-2xl font-black text-white">Painel de Desenvolvimento</h1>
          <span className="text-xs font-bold px-2 py-0.5 rounded bg-amber-500/20 text-amber-400 border border-amber-500/30">
            ADMIN
          </span>
        </div>
        <p className="text-white/40 text-sm">
          Kevin analisa o codebase e cria a spec. Davi implementa. Kevin revisa.
        </p>
      </div>

      {/* Agent cards */}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="card-glass rounded-2xl p-5 border-l-4 border-violet-500">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-2xl">🏛️</span>
            <div>
              <p className="font-bold text-white">Kevin</p>
              <p className="text-white/40 text-xs">Arquiteto & Revisor</p>
            </div>
          </div>
          <p className="text-white/50 text-sm">
            Lê o codebase, identifica padrões e cria especificações técnicas detalhadas.
            Revisa o código do Davi antes de finalizar.
          </p>
        </div>
        <div className="card-glass rounded-2xl p-5 border-l-4 border-cyan-500">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-2xl">💻</span>
            <div>
              <p className="font-bold text-white">Davi</p>
              <p className="text-white/40 text-xs">Desenvolvedor Backend</p>
            </div>
          </div>
          <p className="text-white/50 text-sm">
            Implementa a spec do Kevin: cria arquivos Python/TypeScript, valida
            sintaxe e escreve código limpo seguindo as convenções do projeto.
          </p>
        </div>
      </div>

      {/* Task input */}
      <div className="card-glass rounded-2xl p-6">
        <h2 className="font-bold text-white mb-4">📝 Nova Tarefa</h2>
        <textarea
          value={task}
          onChange={e => setTask(e.target.value)}
          placeholder="Descreva a tarefa de desenvolvimento em detalhes..."
          rows={4}
          className="w-full bg-white/[0.04] border border-white/10 rounded-xl px-4 py-3 text-white text-sm resize-none focus:outline-none focus:border-violet-500/60 placeholder:text-white/25"
        />
        <div className="flex flex-wrap gap-2 mt-3 mb-4">
          {EXAMPLES.map(ex => (
            <button
              key={ex}
              onClick={() => setTask(ex)}
              className="text-xs px-3 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-white/40 hover:text-white/70 hover:border-white/20 transition-colors text-left"
            >
              {ex.slice(0, 55)}...
            </button>
          ))}
        </div>
        <button
          onClick={runTask}
          disabled={loading || !task.trim() || isRunning}
          className="w-full py-3 bg-violet-600 hover:bg-violet-500 disabled:bg-violet-900 disabled:cursor-not-allowed text-white font-bold rounded-xl transition-colors flex items-center justify-center gap-2"
        >
          {isRunning ? (
            <>
              <span className="animate-spin">⚙️</span> Kevin e Davi estão trabalhando...
            </>
          ) : loading ? "Iniciando..." : "▶ Executar Kevin + Davi"}
        </button>
      </div>

      {/* Active session output */}
      {session && (
        <div className="card-glass rounded-2xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-bold text-white">Sessão em andamento</h2>
            <span className={`text-xs font-semibold px-3 py-1.5 rounded-full border ${STATUS_COLORS[session.status]}`}>
              {STATUS_LABELS[session.status]}
            </span>
          </div>
          <p className="text-white/50 text-sm bg-white/[0.03] rounded-lg px-3 py-2 italic">"{session.task}"</p>

          {/* Tabs */}
          <div className="flex gap-2 border-b border-white/10 pb-1">
            {(["kevin", "davi", "review"] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
                  activeTab === tab
                    ? "text-white border-b-2 border-violet-500"
                    : "text-white/40 hover:text-white/60"
                }`}
              >
                {tab === "kevin" ? "🏛️ Spec do Kevin" : tab === "davi" ? "💻 Código do Davi" : "🔍 Revisão"}
              </button>
            ))}
          </div>

          <div className="bg-black/40 rounded-xl p-4 min-h-[200px] max-h-[500px] overflow-y-auto">
            {activeTab === "kevin" && (
              session.kevin_spec
                ? <pre className="text-green-300 text-xs whitespace-pre-wrap font-mono leading-relaxed">{session.kevin_spec}</pre>
                : <p className="text-white/25 text-sm text-center pt-8">Kevin ainda está analisando o codebase...</p>
            )}
            {activeTab === "davi" && (
              session.davi_output
                ? <pre className="text-cyan-300 text-xs whitespace-pre-wrap font-mono leading-relaxed">{session.davi_output}</pre>
                : <p className="text-white/25 text-sm text-center pt-8">Davi aguarda a spec do Kevin...</p>
            )}
            {activeTab === "review" && (
              session.review_output
                ? <pre className="text-violet-300 text-xs whitespace-pre-wrap font-mono leading-relaxed">{session.review_output}</pre>
                : <p className="text-white/25 text-sm text-center pt-8">Kevin ainda não revisou a implementação...</p>
            )}
          </div>

          {session.error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3 text-red-300 text-sm">
              ❌ {session.error}
            </div>
          )}
        </div>
      )}

      {/* Session history */}
      {sessions.length > 0 && (
        <div className="card-glass rounded-2xl p-6">
          <h2 className="font-bold text-white mb-4">📋 Histórico de Sessões</h2>
          <div className="space-y-2">
            {sessions.map(s => (
              <button
                key={s.id}
                onClick={() => setSession(s)}
                className="w-full flex items-center justify-between p-3 rounded-xl bg-white/[0.03] border border-white/[0.06] hover:border-white/20 transition-colors text-left"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-white/80 text-sm truncate">{s.task}</p>
                  <p className="text-white/30 text-xs mt-0.5">
                    {s.started_at ? new Date(s.started_at).toLocaleString("pt-BR") : "—"}
                  </p>
                </div>
                <span className={`text-xs px-2.5 py-1 rounded-full border shrink-0 ml-3 ${STATUS_COLORS[s.status]}`}>
                  {STATUS_LABELS[s.status]}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
