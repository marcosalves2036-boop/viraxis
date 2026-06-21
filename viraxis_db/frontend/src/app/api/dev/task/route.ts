import { NextRequest, NextResponse } from "next/server";
const API = process.env.BACKEND_URL || "https://viraxis.onrender.com";

export async function POST(req: NextRequest) {
  const token = req.headers.get("authorization") ?? "";
  try {
    const body = await req.json();
    const res = await fetch(`${API}/dev/task`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: token },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    try { return NextResponse.json(JSON.parse(text), { status: res.status }); }
    catch { return NextResponse.json({ detail: text }, { status: res.status }); }
  } catch (err) {
    return NextResponse.json({ detail: String(err) }, { status: 500 });
  }
}
