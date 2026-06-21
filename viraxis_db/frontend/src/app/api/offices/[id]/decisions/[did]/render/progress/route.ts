import { NextRequest, NextResponse } from "next/server";
const API = process.env.BACKEND_URL || "https://viraxis.onrender.com";
type Params = { params: Promise<{ id: string; did: string }> };

export async function GET(req: NextRequest, { params }: Params) {
  const { id, did } = await params;
  const token = req.headers.get("authorization") ?? "";
  try {
    const res = await fetch(`${API}/offices/${id}/decisions/${did}/render/progress`, {
      headers: { Authorization: token },
    });
    const text = await res.text();
    try { return NextResponse.json(JSON.parse(text), { status: res.status }); }
    catch { return NextResponse.json({ detail: text }, { status: res.status }); }
  } catch (err) {
    return NextResponse.json({ detail: String(err) }, { status: 500 });
  }
}
