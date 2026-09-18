// SPDX-License-Identifier: FSL-1.1-ALv2
// Copyright 2026 SymonSaysLLC
// SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
/** @type {import('next').NextConfig} */
// Strictly local by construction. No remote image hosts, no telemetry, no external
// origin anywhere in this file — rules section 5.6 requires that no hostname other
// than loopback and the estate's own units appears in the web layer's configuration.
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // A release ships the interface as one directory that runs with `node server.js`
  // and nothing else installed — the standalone output is what makes that true.
  output: "standalone",
  // No image optimisation here, so the optional image library — and the LGPL-3 native
  // codec it drags in — is neither needed at run time nor traced into the bundle. The
  // ship gate refuses that codec; this is where it is kept out.
  images: { unoptimized: true },
  outputFileTracingExcludes: { "*": ["node_modules/sharp/**", "node_modules/@img/**", "node_modules/.pnpm/sharp@*/**", "node_modules/.pnpm/@img+*/**"] },
  // The gateway is loopback-only and this interface is served from the same host,
  // so requests are same-origin through the rewrite below rather than CORS.
  async rewrites() {
    const gateway = process.env.SYM_GW_URL ?? "http://127.0.0.1:9001";
    const control = process.env.SYM_API_URL ?? "http://127.0.0.1:8800";
    return [
      { source: "/gw/:path*", destination: `${gateway}/:path*` },
      { source: "/ctl/:path*", destination: `${control}/:path*` },
    ];
  },
};
export default nextConfig;
