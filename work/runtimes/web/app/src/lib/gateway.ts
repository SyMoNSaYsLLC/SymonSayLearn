/* The typed client for this estate's own surfaces.
 *
 * Two upstreams, both loopback, both reached through the rewrites in
 * next.config.mjs so the browser only ever talks to its own origin:
 *
 *   /gw/*   -> the dialect gateway, 127.0.0.1:9001
 *   /ctl/*  -> the control plane,   127.0.0.1:8800
 *
 * The credential never reaches the browser. Requests that need it go through a
 * route handler on the server side of this application, which reads the same
 * 0600 file the gateway reads. Putting a bearer token in client JavaScript would
 * hand it to anything that can read the page, and "it is only loopback" is not a
 * boundary once a browser is in the path.
 */

export type FamilyTier = "sonnet" | "opus" | "haiku" | "fable" | "mythos";
export type Surface = "chat" | "code" | "cowork";

/** A row of GET /v1/models, exactly as the dialect returns it. */
export interface ModelRow {
  type: "model";
  id: string;
  display_name: string;
  created_at: string;
  description?: string;
  anthropic_family_tier?: FamilyTier;
  is_family_default?: boolean;
  max_input_tokens?: number;
  max_output_tokens?: number;
}

/** GET /v1/models/{id} adds first-party provenance under a namespaced key. */
export interface ModelDetail extends ModelRow {
  "x-symoneural"?: {
    surface: Surface;
    unit: string;
    worker_model: string;
    upstream: string;
    licence: string;
    shares_weights_with: string[];
  };
}

export interface ModelList {
  data: ModelRow[];
  has_more: boolean;
  first_id: string | null;
  last_id: string | null;
}

export interface ReadyState {
  status: "ready" | "unavailable";
  reason?: string;
  chat_unit: string;
  models?: string[];
}

/** One unit of the rack, as GET /api/status reports it. */
export interface UnitState {
  unit: string;
  resource: "GPU" | "CPU" | "NET";
  state: "READY" | "BUSY" | "OFFLINE" | "QUEUED" | "UNCONFIGURED";
  port: number;
  height: number;
  description: string;
  backed_by: string[];
}

export interface RackState {
  uptime_s: number;
  gpu_lock: { unit: string; pid: number; held_for_s: number; alive: boolean } | null;
  units: UnitState[];
}

/** The dialect's error envelope. Never FastAPI's `detail`. */
export interface DialectError {
  type: "error";
  error: { type: string; message: string };
}

export class GatewayError extends Error {
  constructor(
    readonly status: number,
    readonly kind: string,
    message: string,
    readonly requestId?: string,
  ) {
    super(message);
    this.name = "GatewayError";
  }
}

/* A failed request must say WHICH failure it was. "Could not load models" sends
 * an operator to the wrong place; "the chat unit is not answering on 8802"
 * sends them to the right one. So the envelope is parsed rather than discarded.
 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { ...init, cache: "no-store" });
  } catch (cause) {
    throw new GatewayError(0, "unreachable", `${path} did not answer: ${String(cause)}`);
  }

  const requestId = res.headers.get("x-request-id") ?? undefined;
  const text = await res.text();

  let parsed: unknown = undefined;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      /* fall through; the raw text becomes the message */
    }
  }

  if (!res.ok) {
    const envelope = parsed as DialectError | undefined;
    if (envelope?.type === "error" && envelope.error) {
      throw new GatewayError(res.status, envelope.error.type, envelope.error.message, requestId);
    }
    throw new GatewayError(res.status, "http_error", text.slice(0, 500) || `HTTP ${res.status}`, requestId);
  }

  return parsed as T;
}

/* ---- public, no credential needed ---------------------------------------- */

export function gatewayHealth(): Promise<{ status: string; uptime_s: number }> {
  return request("/gw/health");
}

export function rack(): Promise<RackState> {
  return request("/ctl/api/status");
}

/* ---- credentialed: served by this application's own route handlers --------
 * These call /api/* on THIS server, which attaches the credential and forwards
 * to the gateway. The token stays on the server.
 */

export function models(): Promise<ModelList> {
  return request("/api/models");
}

export function model(id: string): Promise<ModelDetail> {
  return request(`/api/models/${encodeURIComponent(id)}`);
}

export function ready(): Promise<ReadyState> {
  return request("/api/ready");
}

/** Tier ordering for display. Mirrors the dialect's own list so a picker shows
 *  them in a stable order rather than whatever the registry happened to emit. */
export const TIER_ORDER: FamilyTier[] = ["haiku", "sonnet", "opus", "fable", "mythos"];

export function sortByTier(rows: ModelRow[]): ModelRow[] {
  return [...rows].sort((a, b) => {
    const ai = a.anthropic_family_tier ? TIER_ORDER.indexOf(a.anthropic_family_tier) : 99;
    const bi = b.anthropic_family_tier ? TIER_ORDER.indexOf(b.anthropic_family_tier) : 99;
    return ai - bi || a.id.localeCompare(b.id);
  });
}

/** Which surface a card drives, for grouping in the interface. */
export const SURFACE_LABEL: Record<Surface, string> = {
  chat: "Chat",
  code: "Code",
  cowork: "Cowork",
};
