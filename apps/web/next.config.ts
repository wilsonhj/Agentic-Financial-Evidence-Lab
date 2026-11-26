import { join } from "node:path";

import type { NextConfig } from "next";

// Inline scripts: the theme boot snippet and Next's streaming runtime.
// unsafe-eval: Ajv compiles JSON Schema guards with new Function in the
// browser (extraction contracts, and reader response checks). React also
// uses eval under next dev. External script origins stay blocked.
const contentSecurityPolicy = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  // @fel/contracts ships TypeScript source (main: src/index.ts); transpile it
  // inside the Next build instead of requiring a prebuilt dist.
  transpilePackages: ["@fel/contracts"],
  // Pin the workspace root so Turbopack does not infer a parent checkout.
  turbopack: {
    root: join(import.meta.dirname, "../.."),
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: contentSecurityPolicy },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
        ],
      },
    ];
  },
};

export default nextConfig;
