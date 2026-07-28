import { NextRequest, NextResponse } from "next/server";

const API = process.env.BACKEND_URL || "https://viraxis.onrender.com";

export async function GET(req: NextRequest) {
  const token = req.headers.get("authorization") ?? "";
  const qs = req.nextUrl.searchParams.toString();
  const url = `${API}/analytics/timeline${qs ? `?${qs}` : ""}`;
  try {
    const res = await fetch(url, {
      headers: { Authorization: token },
      cache: "no-store",
    });
    const text = await res.text();
    try {
      return NextResponse.json(JSON.parse(text), { status: res.status });
    } catch {
      return NextResponse.json({ detail: text }, { status: res.status });
    }
  } catch {
    return NextResponse.json(
      { detail: "Servidor temporariamente indisponível. Aguarde 30 segundos e tente novamente." },
      { status: 503 }
    );
  }
}
