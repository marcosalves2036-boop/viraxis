import { NextRequest, NextResponse } from "next/server";

const API = process.env.BACKEND_URL || "https://viraxis.onrender.com";

export async function POST(req: NextRequest) {
  const token = req.headers.get("authorization") ?? "";

  // Repassa o FormData diretamente ao backend
  const formData = await req.formData();

  const res = await fetch(`${API}/raw-videos/upload`, {
    method: "POST",
    headers: {
      Authorization: token,
      // NÃO setar Content-Type — deixar o fetch gerar o boundary correto
    },
    body: formData,
  });

  const text = await res.text();
  try {
    return NextResponse.json(JSON.parse(text), { status: res.status });
  } catch {
    return NextResponse.json({ detail: text }, { status: res.status });
  }
}

// Aumentar limite de body para 512 MB (Render tem timeout de 30s para free tier)
export const config = {
  api: {
    bodyParser: false,
    responseLimit: false,
  },
};
