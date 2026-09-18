// SPDX-License-Identifier: FSL-1.1-ALv2
// Copyright 2026 SymonSaysLLC
// SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
/* Server-side access to the gateway. Never imported by a client component.
 *
 * The credential is read here and nowhere else. It was previously re-implemented in
 * every page that needed it, which is how a rule like "the value never reaches the
 * browser" quietly stops being true: one copy forgets. One reader, one place.
 *
 * The `server-only` package would make that a build error. It is not in the dependency
 * set and the package manager cannot reach a registry from this host, so the guard is
 * enforced at runtime instead: the module throws if it is ever evaluated in a browser.
 * That is weaker than a build failure — it fires on first use rather than at compile
 * time — and it is recorded here rather than left silent. Adding `server-only` is the
 * proper fix the next time dependencies are resolved.
 */
if (typeof window !== "undefined") {
  throw new Error("lib/server is server-side only: it reads the gateway credential");
}

export const GATEWAY = process.env.SYM_GW_URL ?? "http://127.0.0.1:9001";

export interface Credential {
  value: string;
  /** First 16 hex characters of the sha256. Safe to render; the value never is. */
  fingerprint: string;
}

export async function credential(): Promise<Credential | null> {
  const { readFile } = await import("node:fs/promises");
  const { createHash } = await import("node:crypto");
  const { homedir } = await import("node:os");
  const path = process.env.SYM_GW_KEY_FILE ?? `${homedir()}/.config/symoneural/gateway-9001.key`;
  try {
    const value = (await readFile(path, "utf8")).trim();
    if (!value) return null;
    return { value, fingerprint: createHash("sha256").update(value).digest("hex").slice(0, 16) };
  } catch {
    return null;
  }
}

/** The dialect's own error envelope, so a failure says which failure it was. */
export function dialectError(status: number, type: string, message: string): Response {
  return new Response(JSON.stringify({ type: "error", error: { type, message } }), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** Forward to the gateway with the credential attached. Returns the raw Response so
 *  a streaming caller can hand the body straight back. */
export async function toGateway(path: string, init: RequestInit = {}): Promise<Response> {
  const key = await credential();
  if (!key) {
    return dialectError(
      503,
      "not_configured",
      "no credential at the configured key file; the deployment is unconfigured, not broken",
    );
  }
  const headers = new Headers(init.headers);
  headers.set("authorization", `Bearer ${key.value}`);
  headers.set("anthropic-version", "2023-06-01");
  if (init.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  try {
    return await fetch(`${GATEWAY}${path}`, { ...init, headers, cache: "no-store" });
  } catch (cause) {
    return dialectError(502, "unreachable", `the gateway did not answer: ${String(cause)}`);
  }
}
