import { NextRequest, NextResponse } from "next/server";
const API = process.env.BACKEND_URL || "https://viraxis.onrender.com";

type Params = { params: { id: string; did: string } };

export async function GET(req: NextRequest, { params }: Params) {
  const token = req.headers.get("authorization") ?? "";
  try {
    const res = await fetch(`${API}/offices/${params.id}/decisions/${params.did}`, {
      headers: { Authorization: token },
    });
    const text = await res.text();
    try { return NextResponse.json(JSON.parse(text), { status: res.status }); }
    catch { return NextResponse.json({ detail: text }, { status: res.status }); }
  } catch (err) {
    return NextResponse.json({ detail: String(err) }, { status: 500 });
  }
}

export async function PATCH(req: NextRequest, { params }: Params) {
  const token = req.headers.get("authorization") ?? "";
  const body = await req.text();
  try {
    const res = await fetch(`${API}/offices/${params.id}/decisions/${params.did}/status`, {
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
