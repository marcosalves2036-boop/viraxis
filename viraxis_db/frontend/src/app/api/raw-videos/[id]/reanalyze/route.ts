import { NextRequest, NextResponse } from "next/server";

const API = process.env.BACKEND_URL || "https://viraxis.onrender.com";

// Proxy para POST /raw-videos/{id}/reanalyze (DAVI) — re-dispara a análise de
// IA de um RawVideo com status=failed, sem exigir novo upload. Usado pelo
// botão "Tentar novamente" da Biblioteca.
//
// Repassa o header `Retry-After` do backend quando o rate limit (10/min por
// usuário) é excedido (429), para que o frontend possa exibir uma contagem
// regressiva em vez de martelar o endpoint.
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const token = req.headers.get("authorization") ?? "";

  const res = await fetch(`${API}/raw-videos/${id}/reanalyze`, {
    method: "POST",
    headers: { Authorization: token, "Content-Type": "application/json" },
  });

  const text = await res.text();
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    data = { detail: text };
  }

  const responseHeaders: Record<string, string> = {};
  const retryAfter = res.headers.get("retry-after");
  if (retryAfter) responseHeaders["Retry-After"] = retryAfter;

  return NextResponse.json(data, { status: res.status, headers: responseHeaders });
}
