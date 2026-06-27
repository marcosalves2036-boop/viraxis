import { NextRequest, NextResponse } from "next/server";

const API = process.env.BACKEND_URL || "https://viraxis.onrender.com";

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const token = req.headers.get("authorization") ?? "";

  const res = await fetch(`${API}/offices/${id}`, {
    method: "DELETE",
    headers: { Authorization: token },
  });

  if (res.status === 204) {
    return new NextResponse(null, { status: 204 });
  }

  const body = await res.text();
  return new NextResponse(body, { status: res.status });
}
