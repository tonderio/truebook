import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";

const FASTAPI_URL = process.env.FASTAPI_URL!;
const FASTAPI_INTERNAL_KEY = process.env.FASTAPI_INTERNAL_KEY!;

async function proxyToFastAPI(req: NextRequest, params: Promise<{ path: string[] }>) {
  const session = await auth();
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { path } = await params;
  const targetPath = `/api/${path.join("/")}`;
  const url = new URL(targetPath, FASTAPI_URL);

  // Forward query params
  req.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.set(key, value);
  });

  const headers = new Headers();
  headers.set("X-Internal-Api-Key", FASTAPI_INTERNAL_KEY);
  headers.set("X-User-Id", session.user.id ?? "");

  // Forward content-type for non-GET requests
  const contentType = req.headers.get("content-type");
  if (contentType) {
    headers.set("Content-Type", contentType);
  }

  const isBodyMethod = ["POST", "PUT", "PATCH"].includes(req.method);

  const response = await fetch(url.toString(), {
    method: req.method,
    headers,
    body: isBodyMethod ? req.body : undefined,
    // @ts-expect-error -- duplex is needed for streaming body
    duplex: isBodyMethod ? "half" : undefined,
  });

  // For blob responses (Excel exports), stream them through
  const responseContentType = response.headers.get("content-type");
  if (
    responseContentType &&
    !responseContentType.includes("application/json")
  ) {
    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        "content-type": responseContentType,
        ...(response.headers.get("content-disposition") && {
          "content-disposition": response.headers.get("content-disposition")!,
        }),
      },
    });
  }

  const data = await response.json().catch(() => null);
  return NextResponse.json(data, { status: response.status });
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyToFastAPI(req, ctx.params);
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyToFastAPI(req, ctx.params);
}

export async function DELETE(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyToFastAPI(req, ctx.params);
}
