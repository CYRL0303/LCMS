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

export interface RuntimeCredentials {
  qwenApiKey?: string;
  githubToken?: string;
  gitlabToken?: string;
  webhookSecret?: string;
}

export interface ApiCallOptions {
  credentials?: RuntimeCredentials;
}

export async function getJson<T>(
  path: string,
  options: ApiCallOptions = {},
): Promise<ApiCallResult<T>> {
  return requestJson<T>("GET", path, undefined, options);
}

export async function postJson<T>(
  path: string,
  body: unknown,
  options: ApiCallOptions = {},
): Promise<ApiCallResult<T>> {
  return requestJson<T>("POST", path, body, options);
}

export async function deleteJson<T>(
  path: string,
  options: ApiCallOptions = {},
): Promise<ApiCallResult<T>> {
  return requestJson<T>("DELETE", path, undefined, options);
}

function endpoint(path: string): string {
  const normalizedBase = apiBase.endsWith("/") ? apiBase.slice(0, -1) : apiBase;
  return `${normalizedBase}${path}`;
}

async function requestJson<T>(
  method: "GET" | "POST" | "DELETE",
  path: string,
  body?: unknown,
  options: ApiCallOptions = {},
): Promise<ApiCallResult<T>> {
  const started = performance.now();
  const response = await fetch(endpoint(path), {
    method,
    headers: requestHeaders(body, options.credentials),
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

function requestHeaders(
  body: unknown,
  credentials: RuntimeCredentials | undefined,
): Headers | undefined {
  const headers = new Headers();
  let hasHeaders = false;
  if (body !== undefined) {
    headers.set("Content-Type", "application/json");
    hasHeaders = true;
  }
  if (credentials?.qwenApiKey) {
    headers.set("X-LegacyPilot-Qwen-Api-Key", credentials.qwenApiKey);
    hasHeaders = true;
  }
  if (credentials?.githubToken) {
    headers.set("X-LegacyPilot-GitHub-Token", credentials.githubToken);
    hasHeaders = true;
  }
  if (credentials?.gitlabToken) {
    headers.set("X-LegacyPilot-GitLab-Token", credentials.gitlabToken);
    hasHeaders = true;
  }
  if (credentials?.webhookSecret) {
    headers.set("X-LegacyPilot-Webhook-Secret", credentials.webhookSecret);
    hasHeaders = true;
  }
  return hasHeaders ? headers : undefined;
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
