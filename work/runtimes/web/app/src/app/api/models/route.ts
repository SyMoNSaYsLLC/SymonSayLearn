// SPDX-License-Identifier: FSL-1.1-ALv2
// Copyright 2026 SymonSaysLLC
// SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
/* GET /api/models — the registry, with the credential attached on this side. */
import { toGateway } from "@/lib/server";

export const dynamic = "force-dynamic";

export async function GET() {
  const r = await toGateway("/v1/models");
  return new Response(r.body, { status: r.status, headers: { "content-type": "application/json" } });
}
