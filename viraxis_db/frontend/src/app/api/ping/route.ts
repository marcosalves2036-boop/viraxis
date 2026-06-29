import { NextResponse } from "next/server";

const API = process.env.BACKEND_URL || "https://viraxis.onrender.com";

export async function GET() {
  try {
    const res = await fetch(`${API}/health`, { signal: AbortSignal.timeout(8000) });
    return NextResponse.json({ ok: res.ok, status: res.status });
  } catch {
    return NextResponse.json({ ok: false }, { status: 503 });
  }
}
