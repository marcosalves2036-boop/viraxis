import { NextRequest, NextResponse } from "next/server";

const BACKEND = "https://viraxis.onrender.com";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const auth = req.headers.get("Authorization") ?? "";
  const res = await fetch(
    `${BACKEND}/brain/batch-suggest?${searchParams.toString()}`,
    { headers: { Authorization: auth }, cache: "no-store" }
  );
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
