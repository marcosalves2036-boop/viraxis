import { NextRequest, NextResponse } from "next/server";
const API = "http://localhost:8000";

export async function GET(req: NextRequest, { params }: { params: { id: string } }) {
  const token = req.headers.get("authorization") ?? "";
  const qs = req.nextUrl.searchParams.toString();
  const url = `${API}/offices/${params.id}/decisions${qs ? `?${qs}` : ""}`;
  try {
    const res = await fetch(url, { headers: { Authorization: token } });
    const text = await res.text();
    try { return NextResponse.json(JSON.parse(text), { status: res.status }); }
    catch { return NextResponse.json({ detail: text }, { status: res.status }); }
  } catch (err) {
    return NextResponse.json({ detail: String(err) }, { status: 500 });
  }
}
