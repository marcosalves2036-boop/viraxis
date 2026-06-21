import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL ?? "https://viraxis.onrender.com";

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string; itemId: string }> }
) {
  const { id, itemId } = await params;
  const auth = req.headers.get("authorization") ?? "";
  const r = await fetch(`${BACKEND}/offices/${id}/content/${itemId}/reject`, {
    method: "PATCH",
    headers: { Authorization: auth },
  });
  const body = await r.json().catch(() => ({}));
  return NextResponse.json(body, { status: r.status });
}
