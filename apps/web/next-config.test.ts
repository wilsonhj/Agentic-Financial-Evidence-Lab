import { describe, expect, it } from "vitest";

import nextConfig from "./next.config";

describe("browser hardening headers", () => {
  it("sets them on every route", async () => {
    expect(nextConfig.headers).toBeTypeOf("function");
    const previous = process.env.NODE_ENV;
    process.env.NODE_ENV = "production";
    let routes: Awaited<ReturnType<NonNullable<typeof nextConfig.headers>>>;
    try {
      routes = await nextConfig.headers!();
    } finally {
      process.env.NODE_ENV = previous;
    }
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
    expect(directive(policy, "default-src")).toBe("default-src 'self'");
    expect(directive(policy, "script-src")).toBe("script-src 'self' 'unsafe-inline' 'unsafe-eval'");
    expect(directive(policy, "style-src")).toBe("style-src 'self' 'unsafe-inline'");
    expect(policy).toContain("img-src 'self' data: blob:");
    expect(policy).toContain("font-src 'self'");
    expect(policy).toContain("connect-src 'self'");
    expect(policy).toContain("object-src 'none'");
    expect(policy).toContain("base-uri 'self'");
    expect(policy).toContain("form-action 'self'");
    expect(directive(policy, "frame-ancestors")).toBe("frame-ancestors 'none'");
  });

  it("keeps eval available in development, where React and Ajv both need it", async () => {
    const previous = process.env.NODE_ENV;
    process.env.NODE_ENV = "development";
    try {
      const routes = await nextConfig.headers!();
      const policy = routes[0]?.headers.find(
        (header) => header.key === "Content-Security-Policy",
      )?.value;
      expect(directive(policy ?? "", "script-src")).toBe(
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
      );
      expect(policy ?? "").not.toContain("https:");
    } finally {
      process.env.NODE_ENV = previous;
    }
  });
});

function directive(policy: string, name: string): string {
  return (
    policy
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith(`${name} `)) ?? ""
  );
}
