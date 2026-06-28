import { NextRequest, NextResponse } from "next/server";

const API = process.env.BACKEND_URL || "https://viraxis.onrender.com";

type Params = { params: Promise<{ id: string }> };

export async function GET(req: NextRequest, { params }: Params) {
  const { id } = await params;
  const token = req.headers.get("authorization") ?? "";
  const res = await fetch(`${API}/raw-videos/${id}`, {
    headers: { Authorization: token },
  });
  const text = await res.text();
  try {
    return NextResponse.json(JSON.parse(text), { status: res.status });
  } catch {
    return NextResponse.json({ detail: text }, { status: res.status });
  }
}

export async function PATCH(req: NextRequest, { params }: Params) {
  const { id } = await params;
  const token = req.headers.get("authorization") ?? "";
  const body = await req.json();
  const res = await fetch(`${API}/raw-videos/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Authorization: token },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  try {
    return NextResponse.json(JSON.parse(text), { status: res.status });
  } catch {
    return NextResponse.json({ detail: text }, { status: res.status });
  }
}

export async function DELETE(req: NextRequest, { params }: Params) {
  const { id } = await params;
  const token = req.headers.get("authorization") ?? "";
  const res = await fetch(`${API}/raw-videos/${id}`, {
    method: "DELETE",
    headers: { Authorization: token },
  });
  if (res.status === 204) return new NextResponse(null, { status: 204 });
  const text = await res.text();
  return new NextResponse(text, { status: res.status });
}
