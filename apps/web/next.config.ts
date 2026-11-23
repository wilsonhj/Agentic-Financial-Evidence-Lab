import { join } from "node:path";

import type { NextConfig } from "next";

const SECURITY_HEADERS = [
  {
    key: "Content-Security-Policy",
    value: "frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'",
  },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
];

const nextConfig: NextConfig = {
  // @fel/contracts ships TypeScript source (main: src/index.ts); transpile it
  // inside the Next build instead of requiring a prebuilt dist.
  transpilePackages: ["@fel/contracts"],
  // Pin the workspace root so Turbopack does not infer a parent checkout.
  turbopack: {
    root: join(import.meta.dirname, "../.."),
  },
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
