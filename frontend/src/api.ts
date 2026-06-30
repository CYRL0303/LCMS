import type { ContractError } from "./contracts";

const defaultApiBase = "/api";

export const apiBase =
  (import.meta.env.VITE_LEGACY_PILOT_API_BASE as string | undefined) || defaultApiBase;

export class ApiRequestError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    super(isContractError(body) ? body.message : `HTTP ${status}`);
    this.name = "ApiRequestError";
    this.status = status;
    this.body = body;
  }
}

export interface ApiCallResult<T> {
  data: T;
  httpStatus: number;
  elapsedMs: number;
}

export async function getJson<T>(path: string): Promise<ApiCallResult<T>> {
  return requestJson<T>("GET", path);
}

export async function postJson<T>(path: string, body: unknown): Promise<ApiCallResult<T>> {
  return requestJson<T>("POST", path, body);
}

function endpoint(path: string): string {
  const normalizedBase = apiBase.endsWith("/") ? apiBase.slice(0, -1) : apiBase;
  return `${normalizedBase}${path}`;
}

async function requestJson<T>(
  method: "GET" | "POST",
  path: string,
  body?: unknown,
): Promise<ApiCallResult<T>> {
  const started = performance.now();
  const response = await fetch(endpoint(path), {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await parseResponse(response);
  const elapsedMs = Math.round(performance.now() - started);
  if (!response.ok) {
    throw new ApiRequestError(response.status, data);
  }
  return {
    data: data as T,
    httpStatus: response.status,
    elapsedMs,
  };
}

async function parseResponse(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return { message: text };
  }
}

export function isContractError(value: unknown): value is ContractError {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.error_code === "string" &&
    typeof candidate.message === "string" &&
    typeof candidate.source_module === "string" &&
    typeof candidate.recoverable === "boolean"
  );
}
