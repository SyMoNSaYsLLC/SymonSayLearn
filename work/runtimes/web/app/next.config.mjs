/** @type {import('next').NextConfig} */
// Strictly local by construction. No remote image hosts, no telemetry, no external
// origin anywhere in this file — rules section 5.6 requires that no hostname other
// than loopback and the estate's own units appears in the web layer's configuration.
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
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
