import { NextRequest, NextResponse } from "next/server";

const API = process.env.BACKEND_URL || "https://viraxis.onrender.com";

export async function GET(req: NextRequest) {
  const token = req.headers.get("authorization") ?? "";
  const res = await fetch(`${API}/users/me`, { headers: { Authorization: token } });
  const text = await res.text();
  try { return NextResponse.json(JSON.parse(text), { status: res.status }); }
  catch { return NextResponse.json({ detail: text }, { status: res.status }); }
}

export async function PATCH(req: NextRequest) {
  const token = req.headers.get("authorization") ?? "";
  const body = await req.json();
  const res = await fetch(`${API}/users/me`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Authorization: token },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  try { return NextResponse.json(JSON.parse(text), { status: res.status }); }
  catch { return NextResponse.json({ detail: text }, { status: res.status }); }
}
