/**
 * Typed fetch wrapper.
 *
 * Every call validates the response with a Zod schema. The server contract
 * drifts loudly when an endpoint changes shape — the client never silently
 * coerces an unexpected response into "good enough".
 */

import { z, ZodTypeAny } from "zod";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

const BASE = typeof window === "undefined" ? process.env.NEXT_PUBLIC_BACKEND_URL || "" : "";

export async function apiGet<T extends ZodTypeAny>(
  path: string,
  schema: T,
  init?: RequestInit
): Promise<z.infer<T>> {
  return apiSend("GET", path, undefined, schema, init);
}

export async function apiPost<T extends ZodTypeAny>(
  path: string,
  body: unknown,
  schema: T,
  init?: RequestInit
): Promise<z.infer<T>> {
  return apiSend("POST", path, body, schema, init);
}

export async function apiPostForm<T extends ZodTypeAny>(
  path: string,
  form: FormData,
  schema: T,
  init?: RequestInit
): Promise<z.infer<T>> {
  return apiSendForm("POST", path, form, schema, init);
}

export async function apiPatch<T extends ZodTypeAny>(
  path: string,
  body: unknown,
  schema: T,
  init?: RequestInit
): Promise<z.infer<T>> {
  return apiSend("PATCH", path, body, schema, init);
}

async function apiSend<T extends ZodTypeAny>(
  method: string,
  path: string,
  body: unknown,
  schema: T,
  init?: RequestInit
): Promise<z.infer<T>> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`${BASE}${path}`, { method, headers, body: payload, ...init });
  if (!res.ok) {
    const text = await safeText(res);
    throw new ApiError(res.status, text);
  }
  const json = await res.json();
  return schema.parse(json);
}

async function apiSendForm<T extends ZodTypeAny>(
  method: string,
  path: string,
  form: FormData,
  schema: T,
  init?: RequestInit
): Promise<z.infer<T>> {
  const res = await fetch(`${BASE}${path}`, { method, body: form, ...init });
  if (!res.ok) {
    const text = await safeText(res);
    throw new ApiError(res.status, text);
  }
  const json = await res.json();
  return schema.parse(json);
}

async function safeText(r: Response): Promise<string> {
  try {
    return await r.text();
  } catch {
    return "<no body>";
  }
}
