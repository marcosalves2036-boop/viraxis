import { NextRequest, NextResponse } from "next/server";

const API = process.env.BACKEND_URL || "https://viraxis.onrender.com";

async function proxy(req: NextRequest, path: string, method: string, withBody = false) {
  const token = req.headers.get("authorization") ?? "";
  const opts: RequestInit = {
    method,
    headers: { "Content-Type": "application/json", Authorization: token },
  };
  if (withBody) opts.body = JSON.stringify(await req.json());
  const res = await fetch(`${API}${path}`, opts);
  const text = await res.text();
  try {
    return NextResponse.json(JSON.parse(text), { status: res.status });
  } catch {
    return NextResponse.json({ detail: text }, { status: res.status });
  }
}

export async function GET(req: NextRequest) {
  return proxy(req, "/offices", "GET");
}

export async function POST(req: NextRequest) {
  return proxy(req, "/offices", "POST", true);
}
