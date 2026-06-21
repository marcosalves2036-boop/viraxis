import { NextRequest, NextResponse } from "next/server";

const API = process.env.BACKEND_URL || "https://viraxis.onrender.com";

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const token = req.headers.get("authorization") ?? "";
  try {
    const res = await fetch(`${API}/offices/${params.id}/brain/run`, {
      method: "POST",
      headers: { Authorization: token },
    });
    const text = await res.text();
    try { return NextResponse.json(JSON.parse(text), { status: res.status }); }
    catch { return NextResponse.json({ detail: text }, { status: res.status }); }
  } catch (err) {
    return NextResponse.json({ detail: String(err) }, { status: 500 });
  }
}
