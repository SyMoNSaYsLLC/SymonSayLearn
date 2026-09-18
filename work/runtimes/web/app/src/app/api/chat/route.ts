// SPDX-License-Identifier: FSL-1.1-ALv2
// Copyright 2026 SymonSaysLLC
// SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
/* POST /api/chat — a streamed completion, with the credential attached here.
 *
 * The browser sends only messages and a model id. This handler attaches the
 * credential and streams the gateway's own event stream straight back, unmodified:
 * the dialect's event order (message_start, content_block_start, deltas,
 * content_block_stop, message_delta, message_stop) is a contract the client already
 * knows how to read, and re-encoding it here would create a second format to keep
 * in step with the first.
 *
 * The body is validated rather than forwarded blindly. A browser is not a trusted
 * caller even on loopback: without a whitelist this route would let a page choose
 * any field of the upstream request, including ones that cost a lot of tokens.
 */
import { toGateway, dialectError } from "@/lib/server";

export const dynamic = "force-dynamic";

/** Generous but finite. A runaway max_tokens on a slow local engine is a hang, not an error. */
const MAX_TOKENS_CEILING = 4096;

interface Incoming {
  model?: unknown;
  messages?: unknown;
  max_tokens?: unknown;
  system?: unknown;
}

export async function POST(req: Request) {
  let body: Incoming;
  try {
    body = (await req.json()) as Incoming;
  } catch {
    return dialectError(400, "invalid_request_error", "the request body is not JSON");
  }

  const model = typeof body.model === "string" ? body.model : "";
  if (!model) return dialectError(400, "invalid_request_error", "model is required");

  if (!Array.isArray(body.messages) || body.messages.length === 0) {
    return dialectError(400, "invalid_request_error", "messages must be a non-empty array");
  }
  const messages = body.messages.map((m) => {
    const r = m as { role?: unknown; content?: unknown };
    return {
      role: r.role === "assistant" ? "assistant" : "user",
      content: typeof r.content === "string" ? r.content : "",
    };
  });
  if (messages.some((m) => !m.content)) {
    return dialectError(400, "invalid_request_error", "every message needs text content");
  }

  const asked = typeof body.max_tokens === "number" ? body.max_tokens : 1024;
  const max_tokens = Math.max(1, Math.min(MAX_TOKENS_CEILING, Math.floor(asked)));

  const upstream: Record<string, unknown> = { model, messages, max_tokens, stream: true };
  if (typeof body.system === "string" && body.system.trim()) upstream.system = body.system;

  const r = await toGateway("/v1/messages", { method: "POST", body: JSON.stringify(upstream) });

  // A non-streaming failure arrives as JSON; hand the envelope through untouched so
  // the client can say which failure it was.
  if (!r.ok) {
    return new Response(r.body, { status: r.status, headers: { "content-type": "application/json" } });
  }

  return new Response(r.body, {
    status: 200,
    headers: {
      "content-type": "text/event-stream; charset=utf-8",
      "cache-control": "no-cache, no-transform",
      connection: "keep-alive",
      // Nothing between the browser and this process should buffer a token stream.
      "x-accel-buffering": "no",
    },
  });
}
