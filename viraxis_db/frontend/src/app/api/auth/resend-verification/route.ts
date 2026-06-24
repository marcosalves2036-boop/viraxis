import { NextRequest, NextResponse } from "next/server";

const API = process.env.BACKEND_URL || "https://viraxis.onrender.com";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const res = await fetch(`${API}/auth/resend-verification`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    try {
      const data = JSON.parse(text);
      return NextResponse.json(data, { status: res.status });
    } catch {
      return NextResponse.json({ detail: text || "Erro interno" }, { status: res.status });
    }
  } catch (err) {
    return NextResponse.json({ detail: String(err) }, { status: 500 });
  }
}
