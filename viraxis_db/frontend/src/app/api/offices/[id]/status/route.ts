import { NextRequest, NextResponse } from "next/server";
const API = process.env.BACKEND_URL || "https://viraxis.onrender.com";

export async function PATCH(req: NextRequest, { params }: { params: { id: string } }) {
  const token = req.headers.get("authorization") ?? "";
  const body = await req.text();
  try {
    const res = await fetch(`${API}/offices/${params.id}/status`, {
      method: "PATCH",
      headers: { Authorization: token, "Content-Type": "application/json" },
      body,
    });
    const text = await res.text();
    try { return NextResponse.json(JSON.parse(text), { status: res.status }); }
    catch { return NextResponse.json({ detail: text }, { status: res.status }); }
  } catch (err) {
    return NextResponse.json({ detail: String(err) }, { status: 500 });
  }
}
