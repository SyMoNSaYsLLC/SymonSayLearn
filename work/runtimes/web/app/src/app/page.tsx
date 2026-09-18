// SPDX-License-Identifier: FSL-1.1-ALv2
// Copyright 2026 SymonSaysLLC
// SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
import { headers } from "next/headers";

export const dynamic = "force-dynamic";

/* The overview.
 *
 * Answers one question on arrival: is this estate serving right now, and by what.
 * Everything on this page is READ LIVE on each request. A dashboard that caches
 * is a dashboard that lies, and the whole point of this page is to be trusted
 * when something is wrong.
 */

interface Probe {
  label: string;
  detail: string;
  state: "ok" | "bad" | "idle";
  note?: string;
}

async function probe(): Promise<{ probes: Probe[]; models: string[]; error?: string }> {
  const gw = process.env.SYM_GW_URL ?? "http://127.0.0.1:9001";
  const ctl = process.env.SYM_API_URL ?? "http://127.0.0.1:8800";
  const probes: Probe[] = [];
  let models: string[] = [];

  // Gateway liveness. Public route, so this works even unconfigured.
  try {
    const r = await fetch(`${gw}/health`, { cache: "no-store", signal: AbortSignal.timeout(2500) });
    probes.push({
      label: "Gateway",
      detail: gw.replace(/^https?:\/\//, ""),
      state: r.ok ? "ok" : "bad",
      note: r.ok ? "answering" : `HTTP ${r.status}`,
    });
  } catch (e) {
    probes.push({ label: "Gateway", detail: gw.replace(/^https?:\/\//, ""), state: "bad", note: "no answer" });
  }

  // Readiness needs the credential, so it goes through this server, never the
  // browser. An unconfigured gateway is a distinct state from a dead one and is
  // reported as such rather than collapsed into "error".
  try {
    const key = await credential();
    if (!key) {
      probes.push({
        label: "Credential",
        detail: "~/.config/symoneural/gateway-9001.key",
        state: "idle",
        note: "not provisioned",
      });
    } else {
      probes.push({ label: "Credential", detail: `sha256 ${key.fingerprint}`, state: "ok", note: "loaded" });
      const r = await fetch(`${gw}/ready`, {
        cache: "no-store",
        headers: { authorization: `Bearer ${key.value}` },
        signal: AbortSignal.timeout(4000),
      });
      const body = (await r.json().catch(() => null)) as { status?: string; models?: string[]; reason?: string } | null;
      models = body?.models ?? [];
      probes.push({
        label: "Chat unit",
        detail: "127.0.0.1:8802",
        state: r.ok && body?.status === "ready" ? "ok" : "bad",
        note: r.ok ? (body?.status ?? "unknown") : (body?.reason ?? `HTTP ${r.status}`),
      });
    }
  } catch (e) {
    probes.push({ label: "Chat unit", detail: "127.0.0.1:8802", state: "bad", note: String(e).slice(0, 80) });
  }

  // The control plane is optional: it serves the rack view, not inference.
  try {
    const r = await fetch(`${ctl}/api/health`, { cache: "no-store", signal: AbortSignal.timeout(2000) });
    probes.push({
      label: "Control plane",
      detail: ctl.replace(/^https?:\/\//, ""),
      state: r.ok ? "ok" : "idle",
      note: r.ok ? "answering" : "not running",
    });
  } catch {
    probes.push({ label: "Control plane", detail: ctl.replace(/^https?:\/\//, ""), state: "idle", note: "not running" });
  }

  return { probes, models };
}

/** Read the same 0600 file the gateway reads. Server side only; the value never
 *  reaches the browser, and only its fingerprint is ever rendered. */
async function credential(): Promise<{ value: string; fingerprint: string } | null> {
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

export default async function Page() {
  await headers(); // opt out of static rendering; this page must be live
  const { probes, models } = await probe();
  const serving = probes.find((p) => p.label === "Chat unit")?.state === "ok";

  return (
    <>
      <header className="page-head">
        <h1 className="page-title">SyMoNeuRaL</h1>
        <p className="page-sub">
          {serving
            ? "Serving from this machine. No request leaves the host."
            : "Not serving yet. The checks below say which part is missing."}
        </p>
      </header>

      <section className="grid" aria-label="Service checks">
        {probes.map((p) => (
          <article key={p.label} className="panel-lifted">
            <div className="card-body stack">
              <div className="between">
                <span className="card-title">{p.label}</span>
                <span className={`dot dot-${p.state}`} aria-hidden="true" />
              </div>
              <div className="mono faint" style={{ fontSize: "var(--text-xs)" }}>
                {p.detail}
              </div>
              <div>
                <span
                  className={
                    p.state === "ok" ? "badge badge-ok" : p.state === "bad" ? "badge badge-bad" : "badge badge-muted"
                  }
                >
                  {p.note}
                </span>
              </div>
            </div>
          </article>
        ))}
      </section>

      {models.length > 0 && (
        <section style={{ marginTop: "var(--space-6)" }} aria-label="Models">
          <h2 style={{ fontSize: "var(--text-lg)", marginBottom: "var(--space-3)" }}>Models</h2>
          <div className="panel">
            <div className="card-body stack">
              {models.map((m) => (
                <div key={m} className="row">
                  <span className="dot dot-ok" aria-hidden="true" />
                  <span className="mono">{m}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}
    </>
  );
}
