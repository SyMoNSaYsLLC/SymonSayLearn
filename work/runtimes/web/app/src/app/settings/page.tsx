// SPDX-License-Identifier: FSL-1.1-ALv2
// Copyright 2026 SymonSaysLLC
// SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
/* What this deployment is actually configured to do.
 *
 * Read live, never from a document. The recurring failure this page exists to prevent is
 * a configuration file that describes a deployment nobody is running: the value that
 * matters is the one the process has, not the one written down. So every row below is
 * the effective value, with its source named — an environment variable, or the default
 * that applies because nothing set it.
 *
 * A credential appears only as a fingerprint. There is no view of this page, and no
 * value of any setting, that causes the secret to be rendered.
 */
import { headers } from "next/headers";
import { credential, GATEWAY } from "@/lib/server";

export const dynamic = "force-dynamic";

interface Setting {
  key: string;
  value: string;
  source: "environment" | "default";
  note?: string;
}

function setting(key: string, fallback: string, note?: string): Setting {
  const raw = process.env[key];
  return { key, value: raw ?? fallback, source: raw ? "environment" : "default", note };
}

async function reachable(url: string, path: string): Promise<string> {
  try {
    const r = await fetch(`${url}${path}`, { cache: "no-store", signal: AbortSignal.timeout(2500) });
    return `HTTP ${r.status}`;
  } catch {
    return "no answer";
  }
}

export default async function Page() {
  await headers();

  const key = await credential();
  const settings: Setting[] = [
    setting("SYM_GW_URL", "http://127.0.0.1:9001", "the dialect gateway this interface calls"),
    setting("SYM_API_URL", "http://127.0.0.1:8800", "the control plane; read-only and supervised elsewhere"),
    setting("SYM_GW_KEY_FILE", "~/.config/symoneural/gateway-9001.key", "read by this server, never by a browser"),
    setting("PORT", "3000", "the port this interface listens on"),
    setting("HOSTNAME", "127.0.0.1", "the address this interface binds"),
  ];

  const control = setting("SYM_API_URL", "http://127.0.0.1:8800");
  const [gwState, ctlState] = await Promise.all([
    reachable(GATEWAY, "/health"),
    reachable(control.value, "/api/health"),
  ]);

  return (
    <>
      <header className="page-head">
        <h1 className="page-title">Settings</h1>
        <p className="page-sub">The values this process is actually using, not the ones written down.</p>
      </header>

      <div className="panel panel-lifted">
        <div className="card-body stack">
          <span className="card-title">Credential</span>
          {key ? (
            <div className="row between">
              <span className="muted">loaded from the configured key file</span>
              <span className="mono">sha256 {key.fingerprint}</span>
            </div>
          ) : (
            <div className="row between">
              <span className="muted">not provisioned — this deployment is unconfigured, not broken</span>
              <span className="mono faint">absent</span>
            </div>
          )}
          <p className="muted" style={{ margin: 0 }}>
            Only the fingerprint is ever shown. The value is read by this server process and is
            never sent to a browser.
          </p>
        </div>
      </div>

      <div className="panel">
        <div className="card-body stack">
          <span className="card-title">Effective configuration</span>
          {settings.map((s) => (
            <div key={s.key} className="row between">
              <div className="stack" style={{ gap: ".1rem" }}>
                <span className="mono">{s.key}</span>
                {s.note ? <span className="muted">{s.note}</span> : null}
              </div>
              <div className="stack" style={{ gap: ".1rem", textAlign: "right" }}>
                <span className="mono">{s.value}</span>
                <span className="mono faint">{s.source}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="card-body stack">
          <span className="card-title">Upstreams, probed just now</span>
          <div className="row between">
            <span className="mono">{GATEWAY}</span>
            <span className="mono">{gwState}</span>
          </div>
          <div className="row between">
            <span className="mono">{control.value}</span>
            <span className="mono">{ctlState}</span>
          </div>
          <p className="muted" style={{ margin: 0 }}>
            A control plane that does not answer is reported as such rather than hidden. It is
            read-only and demo-critical, so it is started by whatever supervises it and never
            by this interface.
          </p>
        </div>
      </div>
    </>
  );
}
