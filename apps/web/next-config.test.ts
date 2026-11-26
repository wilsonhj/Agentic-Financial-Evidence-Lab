import { describe, expect, it } from "vitest";

import nextConfig from "./next.config";

describe("browser hardening headers", () => {
  it("sets them on every route", async () => {
    expect(nextConfig.headers).toBeTypeOf("function");
    const routes = await nextConfig.headers!();
    expect(routes).toHaveLength(1);
    expect(routes[0]?.source).toBe("/:path*");
    const headers = Object.fromEntries(
      (routes[0]?.headers ?? []).map((header) => [header.key, header.value]),
    );
    expect(headers["X-Content-Type-Options"]).toBe("nosniff");
    expect(headers["X-Frame-Options"]).toBe("DENY");
    expect(headers["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
    expect(headers["Permissions-Policy"]).toBe("camera=(), microphone=(), geolocation=()");
    expect(headers["Strict-Transport-Security"]).toBe("max-age=31536000; includeSubDomains");
    const policy = headers["Content-Security-Policy"] ?? "";
    expect(policy).toContain("default-src 'self'");
    expect(policy).toContain("script-src 'self' 'unsafe-inline'");
    expect(policy).toContain("style-src 'self' 'unsafe-inline'");
    expect(policy).toContain("img-src 'self' data: blob:");
    expect(policy).toContain("font-src 'self'");
    expect(policy).toContain("connect-src 'self'");
    expect(policy).toContain("object-src 'none'");
    expect(policy).toContain("base-uri 'self'");
    expect(policy).toContain("form-action 'self'");
    expect(policy).toContain("frame-ancestors 'none'");
  });
});
