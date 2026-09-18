// SPDX-License-Identifier: FSL-1.1-ALv2
// Copyright 2026 SymonSaysLLC
// SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
/* The registry as the gateway actually projects it.
 *
 * Every field here is read live from GET /v1/models; nothing is hardcoded, so this
 * page cannot drift from what a client is offered. The credential is read on the
 * server and never reaches the browser — the same rule the overview page follows.
 *
 * The "offered" column is the one worth having. A client of this dialect filters the
 * rows it will show: a model appears only if its id matches a tier name or contains
 * one of a small set of tokens. MEASURED 2026-09-18: ids that satisfied neither were
 * discovered and then silently dropped, so a client showed an empty picker while
 * every request through the same gateway succeeded. That failure is invisible from
 * the request path, so it is surfaced here.
 */
import { headers } from "next/headers";

export const dynamic = "force-dynamic";

type Row = {
  id: string;
  display_name?: string;
  description?: string;
  anthropic_family_tier?: string;
  is_family_default?: boolean;
  max_input_tokens?: number;
  max_output_tokens?: number;
};

const TIERS = ["sonnet", "opus", "haiku", "fable", "mythos"];
const EXACT = new RegExp(`^(${TIERS.join("|")})(-[\\d.]+)?$`);
const CONTAINS = ["claude", ...TIERS, "anthropic"];

/** The client-side filter, mirrored so we can show whether a row would be offered. */
function offered(id: string): boolean {
  const lower = id.toLowerCase();
  return EXACT.test(lower) || CONTAINS.some((m) => lower.includes(m));
}

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

async function registry(): Promise<{ rows: Row[]; error?: string }> {
  const gw = process.env.SYM_GW_URL ?? "http://127.0.0.1:9001";
  const key = await credential();
  if (!key) return { rows: [], error: "no credential at the configured key file" };
  try {
    const r = await fetch(`${gw}/v1/models`, {
      cache: "no-store",
      headers: { authorization: `Bearer ${key.value}`, "anthropic-version": "2023-06-01" },
      signal: AbortSignal.timeout(5000),
    });
    if (!r.ok) return { rows: [], error: `gateway answered HTTP ${r.status}` };
    const body = (await r.json()) as { data?: Row[] };
    return { rows: body.data ?? [] };
  } catch {
    return { rows: [], error: "the gateway did not answer" };
  }
}

function tokens(n?: number): string {
  if (!n) return "—";
  return n >= 1000 ? `${Math.round(n / 1000)}k` : String(n);
}

export default async function Page() {
  await headers(); // this surface must be live, never prerendered
  const { rows, error } = await registry();
  const dropped = rows.filter((m) => !offered(m.id));

  return (
    <>
      <header className="page-head">
        <h1 className="page-title">Models</h1>
        <p className="page-sub">The registry the gateway projects to every client.</p>
      </header>

      {error ? (
        <div className="panel">
          <div className="card-body stack">
            <span className="badge badge-warn">unavailable</span>
            <p className="muted" style={{ margin: 0 }}>{error}</p>
          </div>
        </div>
      ) : (
        <>
          <div className="panel panel-lifted">
            <div className="card-body stack">
              {rows.map((m) => (
                <div key={m.id} className="row between">
                  <div className="stack" style={{ gap: ".15rem" }}>
                    <span className="card-title">{m.display_name ?? m.id}</span>
                    <span className="mono faint">{m.id}</span>
                    {m.description ? <span className="muted">{m.description}</span> : null}
                  </div>
                  <div className="stack" style={{ gap: ".15rem", textAlign: "right" }}>
                    <span className="mono">
                      {m.anthropic_family_tier ?? "—"}
                      {m.is_family_default ? " · default" : ""}
                    </span>
                    <span className="mono faint">
                      in {tokens(m.max_input_tokens)} · out {tokens(m.max_output_tokens)}
                    </span>
                    <span className={offered(m.id) ? "mono" : "mono faint"}>
                      {offered(m.id) ? "offered by clients" : "clients will drop this row"}
                    </span>
                  </div>
                </div>
              ))}
              {rows.length === 0 ? <p className="muted" style={{ margin: 0 }}>The gateway returned no rows.</p> : null}
            </div>
          </div>

          <div className="panel">
            <div className="card-body stack">
              <span className="card-title">Why a row can be discovered and still not offered</span>
              <p className="muted" style={{ margin: 0 }}>
                A client of this dialect keeps a row only when its id names a tier or carries one of a
                small set of tokens. A row that fails that test is fetched and then dropped, so the
                picker is empty while every request still succeeds. {dropped.length === 0
                  ? "Every row above passes."
                  : `${dropped.length} row(s) above would be dropped: ${dropped.map((d) => d.id).join(", ")}.`}
              </p>
            </div>
          </div>
        </>
      )}
    </>
  );
}
