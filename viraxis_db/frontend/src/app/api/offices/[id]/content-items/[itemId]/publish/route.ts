import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL ?? "https://viraxis.onrender.com";

// Proxy para o endpoint real do PUBLISHER (backend, router content_items.py):
//   POST {BACKEND_URL}/offices/{officeId}/content-items/{itemId}/publish
//   Body:  { targets: [{ platform, social_account_id, caption?, hashtags? }] }
//   200:   { content_item_id, successful_platforms, failed_platforms, message }
//   422:   status do item não permite publicação (precisa estar ready/draft)
//   404:   office/item não encontrado
// O social_account_id deve vir de uma conta já conectada em /dashboard/canais
// (GET /api/social-accounts?office_id=...).
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string; itemId: string }> }
) {
  const { id, itemId } = await params;
  const auth = req.headers.get("authorization") ?? "";

  let payload: { targets?: unknown } = {};
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ detail: "Corpo da requisição inválido." }, { status: 400 });
  }

  if (!Array.isArray(payload.targets) || payload.targets.length === 0) {
    return NextResponse.json(
      { detail: "Informe ao menos uma plataforma/conta de destino (targets)." },
      { status: 400 }
    );
  }

  try {
    const r = await fetch(`${BACKEND}/offices/${id}/content-items/${itemId}/publish`, {
      method: "POST",
      headers: { Authorization: auth, "Content-Type": "application/json" },
      body: JSON.stringify({ targets: payload.targets }),
    });
    const text = await r.text();
    try {
      return NextResponse.json(JSON.parse(text), { status: r.status });
    } catch {
      return NextResponse.json({ detail: text || "Erro desconhecido do backend." }, { status: r.status });
    }
  } catch {
    return NextResponse.json(
      { detail: "Não foi possível conectar ao serviço de publicação. Tente novamente mais tarde." },
      { status: 502 }
    );
  }
}
