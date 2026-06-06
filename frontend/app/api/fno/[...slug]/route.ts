/**
 * FastAPI proxy for all /api/fno/* client-side requests.
 * Runs server-side in Next.js, forwarding to the Python FastAPI backend.
 * FastAPI handles NSE session management, caching, and synthetic fallbacks.
 */

import { NextRequest, NextResponse } from "next/server";

const FASTAPI_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function proxy(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string[] }> },
): Promise<NextResponse> {
  const { slug } = await params;
  const path = "/api/fno/" + slug.join("/");
  const searchParams = request.nextUrl.searchParams.toString();
  const url = `${FASTAPI_URL}${path}${searchParams ? `?${searchParams}` : ""}`;

  const init: RequestInit = {
    method: request.method,
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    const body = await request.text();
    if (body) init.body = body;
  }

  try {
    const res = await fetch(url, init);
    const data = await res.json().catch(() => null);
    if (data === null) {
      return NextResponse.json(
        { error: "FastAPI returned non-JSON" },
        { status: 502 },
      );
    }
    return NextResponse.json(data, {
      status: res.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const DELETE = proxy;
export const PUT = proxy;
export const PATCH = proxy;
