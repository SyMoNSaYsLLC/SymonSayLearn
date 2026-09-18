"use client";
// SPDX-License-Identifier: FSL-1.1-ALv2
// Copyright 2026 SymonSaysLLC
// SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
/* One conversation surface, shared by Chat, Code and Cowork.
 *
 * The browser never holds the credential. It posts to /api/chat on this same origin;
 * that route attaches the credential and streams the gateway's own event stream back
 * unmodified, so what this component parses is the dialect's documented event order
 * rather than a second format invented in the middle.
 *
 * Two content block types arrive. A thinking block is the model reasoning before it
 * answers; it is rendered separately and folded away, because presenting it as the
 * answer misrepresents what the model said, and hiding it entirely misrepresents what
 * the model did.
 */
import { useCallback, useEffect, useRef, useState } from "react";

interface Turn {
  role: "user" | "assistant";
  text: string;
  thinking?: string;
  error?: string;
}

interface ModelRow {
  id: string;
  display_name?: string;
  anthropic_family_tier?: string;
}

export interface SurfaceProps {
  /** Which family tier this surface prefers when it picks a default model. */
  tier: string;
  title: string;
  subtitle: string;
  placeholder: string;
}

export default function ConversationSurface({ tier, title, subtitle, placeholder }: SurfaceProps) {
  const [models, setModels] = useState<ModelRow[]>([]);
  const [model, setModel] = useState<string>("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    fetch("/api/models", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((body: { data?: ModelRow[] }) => {
        const rows = body.data ?? [];
        setModels(rows);
        const preferred = rows.find((m) => m.anthropic_family_tier === tier) ?? rows[0];
        if (preferred) setModel(preferred.id);
      })
      .catch((e) => setNotice(`the registry did not load: ${String(e)}`));
  }, [tier]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const send = useCallback(async () => {
    const text = draft.trim();
    if (!text || busy || !model) return;
    setDraft("");
    setNotice(null);
    const history = [...turns, { role: "user" as const, text }];
    setTurns([...history, { role: "assistant", text: "", thinking: "" }]);
    setBusy(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          model,
          max_tokens: 1024,
          messages: history.map((t) => ({ role: t.role, content: t.text })),
        }),
      });

      if (!res.ok || !res.body) {
        const envelope = await res.json().catch(() => null);
        const message =
          (envelope as { error?: { message?: string } } | null)?.error?.message ?? `HTTP ${res.status}`;
        setTurns((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: "assistant", text: "", error: message };
          return next;
        });
        return;
      }

      // The dialect's stream: named events, each with a JSON data line. Deltas are
      // routed by the index of the block they belong to, which is how a thinking
      // block and a text block stay apart.
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      const kinds = new Map<number, string>();
      let buffer = "";
      let text_ = "";
      let thinking_ = "";

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const dataLine = frame.split("\n").find((l) => l.startsWith("data:"));
          if (!dataLine) continue;
          let payload: Record<string, unknown>;
          try {
            payload = JSON.parse(dataLine.slice(5).trim());
          } catch {
            continue;
          }
          const type = payload.type as string | undefined;
          if (type === "content_block_start") {
            const idx = payload.index as number;
            const block = payload.content_block as { type?: string } | undefined;
            kinds.set(idx, block?.type ?? "text");
          } else if (type === "content_block_delta") {
            const idx = payload.index as number;
            const delta = payload.delta as { text?: string; thinking?: string } | undefined;
            const piece = delta?.text ?? delta?.thinking ?? "";
            if (kinds.get(idx) === "thinking") thinking_ += piece;
            else text_ += piece;
            setTurns((prev) => {
              const next = [...prev];
              next[next.length - 1] = { role: "assistant", text: text_, thinking: thinking_ };
              return next;
            });
          }
        }
      }
    } catch (e) {
      setTurns((prev) => {
        const next = [...prev];
        next[next.length - 1] = { role: "assistant", text: "", error: String(e) };
        return next;
      });
    } finally {
      setBusy(false);
    }
  }, [draft, busy, model, turns]);

  return (
    <>
      <header className="page-head">
        <h1 className="page-title">{title}</h1>
        <p className="page-sub">{subtitle}</p>
      </header>

      {notice ? (
        <div className="panel">
          <div className="card-body stack">
            <span className="badge badge-warn">notice</span>
            <p className="muted" style={{ margin: 0 }}>{notice}</p>
          </div>
        </div>
      ) : null}

      <div className="panel panel-lifted">
        <div className="card-body stack">
          <div className="row between">
            <span className="card-title">Model</span>
            <select
              className="mono"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              disabled={busy || models.length === 0}
            >
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {(m.display_name ?? m.id) + " · " + m.id}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="card-body stack">
          {turns.length === 0 ? (
            <p className="muted" style={{ margin: 0 }}>
              Nothing yet. Everything below stays on this machine.
            </p>
          ) : null}

          {turns.map((t, i) => (
            <div key={i} className="stack" style={{ gap: ".25rem" }}>
              <span className="mono faint">{t.role === "user" ? "you" : "symon"}</span>
              {t.thinking ? (
                <details>
                  <summary className="muted">reasoning</summary>
                  <p className="muted mono" style={{ whiteSpace: "pre-wrap", margin: 0 }}>{t.thinking}</p>
                </details>
              ) : null}
              {t.error ? (
                <p className="mono" style={{ margin: 0 }}>failed: {t.error}</p>
              ) : (
                <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>
                  {t.text}
                  {busy && i === turns.length - 1 && !t.text ? <span className="faint">…</span> : null}
                </p>
              )}
            </div>
          ))}
          <div ref={endRef} />
        </div>
      </div>

      <div className="panel">
        <div className="card-body stack">
          <textarea
            rows={3}
            value={draft}
            placeholder={placeholder}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void send();
            }}
            disabled={busy}
          />
          <div className="row between">
            <span className="muted">Ctrl or Cmd with Enter sends.</span>
            <button onClick={() => void send()} disabled={busy || !draft.trim() || !model}>
              {busy ? "answering…" : "Send"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
