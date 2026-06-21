import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL ?? "https://viraxis.onrender.com";

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ id: string; itemId: string }> }
) {
  const { id, itemId } = await params;
  const auth = req.headers.get("authorization") ?? "";
  const r = await fetch(`${BACKEND}/offices/${id}/content/${itemId}`, {
    method: "DELETE",
    headers: { Authorization: auth },
  });
  if (r.status === 204) return new NextResponse(null, { status: 204 });
  const body = await r.json().catch(() => ({}));
  return NextResponse.json(body, { status: r.status });
}
