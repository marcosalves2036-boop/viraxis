import { NextRequest, NextResponse } from "next/server";
const API = process.env.BACKEND_URL || "https://viraxis.onrender.com";

export async function POST(req: NextRequest) {
  const token = req.headers.get("authorization") ?? "";

  let body: string | undefined;
  const contentType = req.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const json = await req.json().catch(() => null);
    if (json && Object.keys(json).length > 0) body = JSON.stringify(json);
  }

  try {
    const res = await fetch(`${API}/brain/batch-run`, {
      method: "POST",
      headers: {
        Authorization: token,
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      ...(body ? { body } : {}),
    });
    const text = await res.text();
    try { return NextResponse.json(JSON.parse(text), { status: res.status }); }
    catch { return NextResponse.json({ detail: text }, { status: res.status }); }
  } catch (err) {
    return NextResponse.json({ detail: String(err) }, { status: 500 });
  }
}
