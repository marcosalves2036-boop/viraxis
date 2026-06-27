import { NextRequest, NextResponse } from "next/server";

const API = process.env.BACKEND_URL || "https://viraxis.onrender.com";

export async function GET(req: NextRequest) {
  const token = req.headers.get("authorization") ?? "";
  const { searchParams } = new URL(req.url);
  const params = new URLSearchParams();
  if (searchParams.get("office_id")) params.set("office_id", searchParams.get("office_id")!);
  if (searchParams.get("platform")) params.set("platform", searchParams.get("platform")!);

  const res = await fetch(`${API}/social-accounts?${params}`, {
    headers: { Authorization: token },
  });
  const text = await res.text();
  try {
    return NextResponse.json(JSON.parse(text), { status: res.status });
  } catch {
    return NextResponse.json({ detail: text }, { status: res.status });
  }
}
