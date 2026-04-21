const FASTAPI_URL = process.env.FASTAPI_URL!;
const FASTAPI_INTERNAL_KEY = process.env.FASTAPI_INTERNAL_KEY!;

type FetchOptions = {
  method?: string;
  body?: BodyInit | null;
  headers?: Record<string, string>;
  tenantId?: string;
  userId?: string;
};

export async function fastapiRequest<T = unknown>(
  path: string,
  options: FetchOptions = {}
): Promise<T> {
  const { method = "GET", body, headers = {}, tenantId, userId } = options;

  const url = `${FASTAPI_URL}/api${path}`;

  const res = await fetch(url, {
    method,
    body,
    headers: {
      "X-Internal-Api-Key": FASTAPI_INTERNAL_KEY,
      ...(tenantId && { "X-Tenant-Id": tenantId }),
      ...(userId && { "X-User-Id": userId }),
      ...(body && typeof body === "string" && { "Content-Type": "application/json" }),
      ...headers,
    },
  });

  if (!res.ok) {
    const errorText = await res.text().catch(() => "Unknown error");
    throw new Error(`FastAPI ${method} ${path} failed (${res.status}): ${errorText}`);
  }

  const contentType = res.headers.get("content-type");
  if (contentType?.includes("application/json")) {
    return res.json() as Promise<T>;
  }

  return res.text() as unknown as T;
}

export async function fastapiBlob(
  path: string,
  options: FetchOptions = {}
): Promise<Response> {
  const { method = "GET", headers = {}, tenantId, userId } = options;

  const url = `${FASTAPI_URL}/api${path}`;

  return fetch(url, {
    method,
    headers: {
      "X-Internal-Api-Key": FASTAPI_INTERNAL_KEY,
      ...(tenantId && { "X-Tenant-Id": tenantId }),
      ...(userId && { "X-User-Id": userId }),
      ...headers,
    },
  });
}
