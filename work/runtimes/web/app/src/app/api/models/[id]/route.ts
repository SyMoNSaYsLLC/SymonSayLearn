// SPDX-License-Identifier: FSL-1.1-ALv2
// Copyright 2026 SymonSaysLLC
// SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
/* GET /api/models/{id} — one card, with its first-party provenance. */
import { toGateway } from "@/lib/server";

export const dynamic = "force-dynamic";

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const r = await toGateway(`/v1/models/${encodeURIComponent(id)}`);
  return new Response(r.body, { status: r.status, headers: { "content-type": "application/json" } });
}
