// MCP evidence-surface contracts (ADR-0034 decision 8, design contract §6-§7).
// The shared suite (contracts.test.ts) already proves every schema compiles and
// every fixture validates. This file pins the MCP-specific invariants: the
// §7.4 input limits at their boundaries, the no-oracle shapes, the closed
// enums and the evidence_context/coverage_note requirement on every output.
import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import { describe, expect, it } from "vitest";

import { MCP_TOOL_SCHEMAS, SCHEMA_IDS } from "./src/index";

const here = dirname(fileURLToPath(import.meta.url));
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const load = (rel: string): any => JSON.parse(readFileSync(join(here, rel), "utf8"));

const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
for (const file of readdirSync(join(here, "schemas")).filter((f) => f.endsWith(".schema.json"))) {
  ajv.addSchema(load(`schemas/${file}`));
}

const validator = (id: string) => {
  const validate = ajv.getSchema(id);
  if (!validate) throw new Error(`schema not registered: ${id}`);
  return (value: unknown) => validate(value) as boolean;
};
const fixture = (name: string) => structuredClone(load(`fixtures/${name}.json`));
const repeat = (n: number) => "x".repeat(n);

const TOOLS = [
  "resolve_company",
  "list_filings",
  "search_filings",
  "read_filing",
  "get_citation",
  "get_financial_facts",
  "verify_claim",
  "get_corpus_status",
] as const;
const fileName = (tool: string, side: "input" | "output") =>
  `mcp-${tool.replace(/_/g, "-")}-${side}`;

describe("MCP tool registry", () => {
  it("names exactly the eight design-contract tools, in order, each with both schemas", () => {
    expect(Object.keys(MCP_TOOL_SCHEMAS)).toEqual([...TOOLS]);
    for (const tool of TOOLS) {
      expect(tool.length).toBeLessThan(64);
      for (const side of ["input", "output"] as const) {
        const id = MCP_TOOL_SCHEMAS[tool][side];
        expect(id).toBe(`https://contracts.fel.dev/schemas/${fileName(tool, side)}/v1`);
        expect(load(`schemas/${fileName(tool, side)}.schema.json`).$id).toBe(id);
      }
    }
  });

  it("every output requires evidence_context and coverage_note; every input is closed", () => {
    for (const tool of TOOLS) {
      const output = load(`schemas/${fileName(tool, "output")}.schema.json`);
      expect(output.required.slice(0, 2), tool).toEqual(["evidence_context", "coverage_note"]);
      expect(output.properties.evidence_context.$ref).toBe(SCHEMA_IDS.mcpEvidenceContext);
      const valid = validator(MCP_TOOL_SCHEMAS[tool].output);
      for (const member of ["evidence_context", "coverage_note"]) {
        const body = fixture(fileName(tool, "output"));
        delete body[member];
        expect(valid(body), `${tool} without ${member}`).toBe(false);
      }
      const input = load(`schemas/${fileName(tool, "input")}.schema.json`);
      expect(input.additionalProperties, tool).toBe(false);
      expect(
        validator(MCP_TOOL_SCHEMAS[tool].input)({ ...fixture(fileName(tool, "input")), x: 1 }),
      ).toBe(false);
    }
  });

  it("every input that reads evidence accepts as_of and timestamp_mode", () => {
    for (const tool of TOOLS) {
      const input = load(`schemas/${fileName(tool, "input")}.schema.json`);
      expect(input.properties.as_of, tool).toBeDefined();
      expect(input.properties.timestamp_mode.enum, tool).toEqual(["strict", "approximate"]);
    }
  });
});

describe("as_of (design contract §6.1, §7.4)", () => {
  const valid = validator(SCHEMA_IDS.mcpGetCitationInput);
  const withAsOf = (as_of: unknown) => ({ ...fixture("mcp-get-citation-input"), as_of });

  it("accepts an instant with an explicit offset, or a date", () => {
    for (const value of [
      "2024-03-07T14:30:00Z",
      "2024-03-07T09:30:00-05:00",
      "1994-01-01",
      "2024-03-07T14:30:00.123Z",
    ]) {
      expect(valid(withAsOf(value)), value).toBe(true);
    }
  });

  it("rejects naive datetimes, pre-1994 cutoffs and non-strings", () => {
    for (const value of [
      "2024-03-07T14:30:00",
      "2024-03-07 14:30:00Z",
      "1993-12-31",
      "1993-12-31T23:59:59Z",
      "",
      1709821800,
    ]) {
      expect(valid(withAsOf(value)), String(value)).toBe(false);
    }
  });
});

describe("request limits (design contract §7.4)", () => {
  it("query <= 500, top_k <= 20, companies/forms <= 10, periods <= 12", () => {
    const valid = validator(SCHEMA_IDS.mcpSearchFilingsInput);
    const base = fixture("mcp-search-filings-input");
    expect(valid({ ...base, query: repeat(500) })).toBe(true);
    expect(valid({ ...base, query: repeat(501) })).toBe(false);
    expect(valid({ ...base, top_k: 20 })).toBe(true);
    expect(valid({ ...base, top_k: 21 })).toBe(false);
    expect(valid({ ...base, top_k: 0 })).toBe(false);
    const many = (n: number) => Array.from({ length: n }, (_, i) => `C${i}`);
    expect(valid({ ...base, companies: many(10) })).toBe(true);
    expect(valid({ ...base, companies: many(11) })).toBe(false);
    expect(valid({ ...base, forms: many(10) })).toBe(true);
    expect(valid({ ...base, forms: many(11) })).toBe(false);
    expect(valid({ ...base, periods: many(12) })).toBe(true);
    expect(valid({ ...base, periods: many(13) })).toBe(false);
    const resolve = validator(SCHEMA_IDS.mcpResolveCompanyInput);
    expect(resolve({ query: repeat(500) })).toBe(true);
    expect(resolve({ query: repeat(501) })).toBe(false);
  });

  it("limit <= 50 on list_filings and get_financial_facts", () => {
    for (const name of ["mcp-list-filings-input", "mcp-get-financial-facts-input"]) {
      const valid = validator(`https://contracts.fel.dev/schemas/${name}/v1`);
      const base = fixture(name);
      expect(valid({ ...base, limit: 50 }), name).toBe(true);
      expect(valid({ ...base, limit: 51 }), name).toBe(false);
      expect(valid({ ...base, limit: 0 }), name).toBe(false);
    }
  });

  it("claim <= 2000, citations 1..10, quote <= 1000", () => {
    const valid = validator(SCHEMA_IDS.mcpVerifyClaimInput);
    const base = fixture("mcp-verify-claim-input");
    expect(valid({ ...base, claim: repeat(2000) })).toBe(true);
    expect(valid({ ...base, claim: repeat(2001) })).toBe(false);
    const ref = base.citations[0];
    expect(valid({ ...base, citations: Array(10).fill(ref) })).toBe(true);
    expect(valid({ ...base, citations: Array(11).fill(ref) })).toBe(false);
    expect(valid({ ...base, citations: [] })).toBe(false);
    expect(valid({ ...base, citations: [{ ...ref, quote: repeat(1000) }] })).toBe(true);
    expect(valid({ ...base, citations: [{ ...ref, quote: repeat(1001) }] })).toBe(false);
  });

  it("numeric.value is a finite decimal string with at most 34 significant digits", () => {
    const valid = validator(SCHEMA_IDS.mcpVerifyClaimInput);
    const base = fixture("mcp-verify-claim-input");
    const withValue = (value: unknown) => ({ ...base, numeric: { ...base.numeric, value } });
    const digits34 = "1234567890123456789012345678901234";
    for (const value of [
      "0",
      "-0",
      "100",
      "-100.25",
      "0.001",
      "000123",
      digits34,
      `-${digits34}`,
      `0.${digits34}`,
      `0.000${digits34}`,
      `${digits34.slice(0, 20)}.${digits34.slice(20)}`,
      `00${digits34}`,
    ]) {
      expect(valid(withValue(value)), value).toBe(true);
    }
    for (const value of [
      `${digits34}5`,
      `0.${digits34}5`,
      `${digits34.slice(0, 20)}.${digits34.slice(20)}5`,
      "1e6",
      "NaN",
      "Infinity",
      "1.",
      ".5",
      "1_000",
      " 1",
      "1\n",
      "",
      100,
    ]) {
      expect(valid(withValue(value)), JSON.stringify(value)).toBe(false);
    }
  });

  it("numeric.scale is exactly one of NUMERIC_SCALE_EXPONENTS and sign is never an input", () => {
    const valid = validator(SCHEMA_IDS.mcpVerifyClaimInput);
    const base = fixture("mcp-verify-claim-input");
    const withNumeric = (patch: object) => ({ ...base, numeric: { ...base.numeric, ...patch } });
    for (const scale of [0, 3, 6, 9])
      expect(valid(withNumeric({ scale })), String(scale)).toBe(true);
    for (const scale of [-3, 1, 2, 12, 6.0001, "6", null]) {
      expect(valid(withNumeric({ scale })), String(scale)).toBe(false);
    }
    expect(valid(withNumeric({ sign: "positive" }))).toBe(false);
    const schema = load("schemas/mcp-verify-claim-input.schema.json");
    expect(Object.keys(schema.properties.numeric.properties)).toEqual([
      "concept",
      "value",
      "unit",
      "scale",
      "period",
    ]);
  });

  it("cursors are bounded opaque strings", () => {
    const valid = validator(SCHEMA_IDS.mcpListFilingsInput);
    const base = fixture("mcp-list-filings-input");
    expect(valid({ ...base, cursor: repeat(2048) })).toBe(true);
    expect(valid({ ...base, cursor: repeat(2049) })).toBe(false);
    expect(valid({ ...base, cursor: "" })).toBe(false);
  });
});

describe("reference shapes", () => {
  it("get_citation takes span_id xor (document_version_id, start_char, end_char)", () => {
    const valid = validator(SCHEMA_IDS.mcpGetCitationInput);
    const span = "7e4f6d5b-9c8a-4b1d-8e0f-405162738495";
    const dv = "6d3e5c4a-8b7f-4a0c-9d9e-3f4051627384";
    expect(valid({ span_id: span })).toBe(true);
    expect(valid({ document_version_id: dv, start_char: 0, end_char: 4 })).toBe(true);
    expect(valid({})).toBe(false);
    expect(valid({ document_version_id: dv, start_char: 0 })).toBe(false);
    expect(valid({ span_id: span, document_version_id: dv, start_char: 0, end_char: 4 })).toBe(
      false,
    );
    expect(valid({ span_id: span, start_char: 0 })).toBe(false);
  });

  it("read_filing takes document_id xor accession", () => {
    const valid = validator(SCHEMA_IDS.mcpReadFilingInput);
    const doc = "5c2d4b3f-7a6e-4f9b-8c8d-2e3f40516273";
    expect(valid({ document_id: doc })).toBe(true);
    expect(valid({ accession: "0001108524-24-000012" })).toBe(true);
    expect(valid({})).toBe(false);
    expect(valid({ document_id: doc, accession: "0001108524-24-000012" })).toBe(false);
  });
});

describe("evidence context (design contract §6.3)", () => {
  const valid = validator(SCHEMA_IDS.mcpEvidenceContext);

  it("requires every pin, nullable where a pin may not apply", () => {
    for (const key of [
      "effective_as_of",
      "timestamp_mode",
      "temporal_guarantee",
      "corpus_version_id",
      "index_version_id",
      "parser_version",
      "verifier_version",
      "document_version_id",
      "filters",
    ]) {
      const body = fixture("mcp-evidence-context");
      delete body[key];
      expect(valid(body), key).toBe(false);
    }
    expect(valid({ ...fixture("mcp-evidence-context"), corpus_version_id: null })).toBe(false);
  });

  it("ties temporal_guarantee to timestamp_mode", () => {
    const body = fixture("mcp-evidence-context");
    expect(valid({ ...body, timestamp_mode: "strict", temporal_guarantee: "none" })).toBe(false);
    expect(valid({ ...body, timestamp_mode: "approximate", temporal_guarantee: "strict" })).toBe(
      false,
    );
    expect(valid({ ...body, timestamp_mode: "approximate", temporal_guarantee: "none" })).toBe(
      true,
    );
  });

  it("rejects a naive effective_as_of", () => {
    expect(
      valid({ ...fixture("mcp-evidence-context"), effective_as_of: "2024-03-07T14:30:00" }),
    ).toBe(false);
  });
});

describe("citation (design contract §7.1)", () => {
  const valid = validator(SCHEMA_IDS.mcpCitation);

  it("the fixture hash is sha256 of its text by code points, and offsets span the text", () => {
    const citation = fixture("mcp-citation");
    const digest = createHash("sha256").update(citation.text, "utf8").digest("hex");
    expect(citation.text_hash).toBe(`sha256:${digest}`);
    expect(citation.end_char - citation.start_char).toBe([...citation.text].length);
    expect(citation.offset_unit).toBe("unicode_code_point");
    expect(citation.untrusted_source_text).toBe(true);
    expect(citation.reader_url).toBeUndefined();
  });

  it("second precision requires a verified accepted_at", () => {
    const citation = fixture("mcp-citation");
    expect(valid({ ...citation, accepted_at: null })).toBe(false);
    expect(valid({ ...citation, timestamp_precision: "approximate", accepted_at: null })).toBe(
      true,
    );
    expect(valid({ ...citation, timestamp_precision: "date" })).toBe(false);
    expect(valid({ ...citation, accepted_at: "2024-03-06T21:14:09" })).toBe(false);
  });

  it("reader_url is optional but must carry span, version, cutoff and corpus scope", () => {
    const citation = fixture("mcp-citation");
    const scoped =
      "https://reader.example/reader/5c2d4b3f-7a6e-4f9b-8c8d-2e3f40516273?span=7e4f6d5b-9c8a-4b1d-8e0f-405162738495&document_version_id=6d3e5c4a-8b7f-4a0c-9d9e-3f4051627384&as_of=2024-03-07T14%3A30%3A00Z&corpus_version_id=a07c9a8e-2f1d-4e4a-9b3c-738495a6b7c8";
    expect(valid({ ...citation, reader_url: scoped })).toBe(true);
    for (const drop of ["span", "document_version_id", "as_of", "corpus_version_id"]) {
      const url = new URL(scoped);
      url.searchParams.delete(drop);
      expect(valid({ ...citation, reader_url: url.toString() }), drop).toBe(false);
    }
  });
});

describe("verification report (design contract §7.2)", () => {
  const valid = validator(SCHEMA_IDS.mcpVerificationReport);
  const report = () => fixture("mcp-verification-report");

  it("claim status is the closed vocabulary without derived", () => {
    const schema = load("schemas/mcp-verification-report.schema.json");
    expect(schema.properties.claim_status.enum).toEqual([
      "supported",
      "partially_supported",
      "contradicted",
      "unsupported",
    ]);
    expect(valid({ ...report(), claim_status: "derived" })).toBe(false);
    expect(schema.$defs.visible.properties.edge_status.enum).toEqual([
      "entailed",
      "partial",
      "contradictory",
      "irrelevant",
    ]);
  });

  it("states that semantic entailment was not evaluated", () => {
    expect(valid({ ...report(), semantic_entailment: "evaluated" })).toBe(false);
    expect(valid({ ...report(), entailment_method: "model" })).toBe(false);
    const body = report();
    delete body.semantic_entailment;
    expect(valid(body)).toBe(false);
  });

  it("an unresolvable citation carries exactly one uninformative shape", () => {
    const notVisible = report().citations[1];
    expect(notVisible).toEqual({
      index: 1,
      checks: { visible: false, hash_valid: null, quote_found: null },
      reason: "not_found",
      edge_status: "irrelevant",
    });
    const leak = (patch: object) => ({ ...report(), citations: [{ ...notVisible, ...patch }] });
    for (const patch of [
      { span_id: "7e4f6d5b-9c8a-4b1d-8e0f-405162738495" },
      { numeric_checks: null },
      { reason: "hidden" },
      { edge_status: "partial" },
      { checks: { visible: false, hash_valid: false, quote_found: null } },
      { accepted_at: "2024-03-06T21:14:09Z" },
    ]) {
      expect(valid(leak(patch)), JSON.stringify(patch)).toBe(false);
    }
  });

  it("integrity failures name their reason and never support the edge", () => {
    const visible = report().citations[0];
    const withCitation = (c: object) => ({ ...report(), citations: [c] });
    const hashBad = { ...visible, checks: { ...visible.checks, hash_valid: false } };
    expect(
      valid(withCitation({ ...hashBad, reason: "hash_mismatch", edge_status: "irrelevant" })),
    ).toBe(true);
    expect(valid(withCitation({ ...hashBad, reason: null }))).toBe(false);
    expect(
      valid(withCitation({ ...hashBad, reason: "hash_mismatch", edge_status: "entailed" })),
    ).toBe(false);
    const quoteBad = { ...visible, checks: { ...visible.checks, quote_found: false } };
    expect(
      valid(withCitation({ ...quoteBad, reason: "quote_not_found", edge_status: "irrelevant" })),
    ).toBe(true);
    expect(valid(withCitation({ ...quoteBad, reason: null }))).toBe(false);
    expect(valid(withCitation({ ...visible, reason: "hash_mismatch" }))).toBe(false);
    expect(
      valid(withCitation({ ...visible, checks: { ...visible.checks, quote_found: null } })),
    ).toBe(true);
  });

  it("reports at most ten citations, by request position", () => {
    const body = report();
    expect(valid({ ...body, citations: Array(11).fill(body.citations[1]) })).toBe(false);
    expect(valid({ ...body, citations: [{ ...body.citations[1], index: 10 }] })).toBe(false);
  });
});

describe("errors (design contract §7.5)", () => {
  const valid = validator(SCHEMA_IDS.mcpError);
  const err = (error: object) => ({ error });

  it("codes are the closed §7.5 set", () => {
    expect(load("schemas/mcp-error.schema.json").properties.error.properties.code.enum).toEqual([
      "not_found",
      "invalid_input",
      "cursor_expired",
      "pin_unavailable",
      "rate_limited",
      "overloaded",
      "deadline_exceeded",
      "unavailable",
      "integrity_error",
    ]);
    expect(valid(err({ code: "NOT_FOUND", message: "m", retryable: false, recovery: "r" }))).toBe(
      false,
    );
  });

  it("not_found is one fixed, uninformative envelope", () => {
    const notFound = {
      code: "not_found",
      message: "No visible evidence matches this reference.",
      retryable: false,
      recovery: "Check the identifier, or search within the current context.",
    };
    expect(valid(err(notFound))).toBe(true);
    expect(valid(err({ ...notFound, message: "Document hidden by the cutoff." }))).toBe(false);
    expect(valid(err({ ...notFound, field: "span_id" }))).toBe(false);
    expect(valid(err({ ...notFound, retry_after_seconds: 1 }))).toBe(false);
    expect(valid(err({ ...notFound, retryable: true }))).toBe(false);
  });

  it("retryable and its hints follow the code", () => {
    const base = { message: "m", recovery: "r" };
    expect(
      valid(err({ ...base, code: "rate_limited", retryable: true, retry_after_seconds: 5 })),
    ).toBe(true);
    expect(valid(err({ ...base, code: "rate_limited", retryable: true }))).toBe(false);
    expect(
      valid(err({ ...base, code: "overloaded", retryable: false, retry_after_seconds: 5 })),
    ).toBe(false);
    expect(
      valid(err({ ...base, code: "unavailable", retryable: true, retry_after_seconds: 30 })),
    ).toBe(true);
    expect(valid(err({ ...base, code: "deadline_exceeded", retryable: true }))).toBe(true);
    expect(valid(err({ ...base, code: "invalid_input", retryable: false }))).toBe(false);
    expect(valid(err({ ...base, code: "invalid_input", retryable: false, field: "top_k" }))).toBe(
      true,
    );
    expect(
      valid(
        err({ ...base, code: "pin_unavailable", retryable: false, field: "corpus_version_id" }),
      ),
    ).toBe(true);
    expect(valid(err({ ...base, code: "pin_unavailable", retryable: false }))).toBe(false);
    expect(
      valid(err({ ...base, code: "cursor_expired", retryable: false, retry_after_seconds: 1 })),
    ).toBe(false);
    expect(valid(err({ ...base, code: "integrity_error", retryable: true }))).toBe(false);
  });
});

describe("get_corpus_status (design contract §6.3 exemption)", () => {
  const valid = validator(SCHEMA_IDS.mcpGetCorpusStatusOutput);

  it("separates replayable coverage from live_status, which is labeled replayable: false", () => {
    const body = fixture("mcp-get-corpus-status-output");
    expect(body.coverage.effective_as_of).toBe(body.evidence_context.effective_as_of);
    expect(valid({ ...body, live_status: { ...body.live_status, replayable: true } })).toBe(false);
    const noLive = structuredClone(body);
    delete noLive.live_status;
    expect(valid(noLive)).toBe(false);
    expect(
      valid({
        ...body,
        coverage: {
          ...body.coverage,
          active_corpus_version_id: body.evidence_context.corpus_version_id,
        },
      }),
    ).toBe(false);
  });

  it("takes as_of and both pins as inputs", () => {
    const schema = load("schemas/mcp-get-corpus-status-input.schema.json");
    expect(Object.keys(schema.properties).sort()).toEqual(
      ["as_of", "corpus_version_id", "index_version_id", "timestamp_mode"].sort(),
    );
  });

  it("no other tool output carries live state", () => {
    for (const tool of TOOLS.filter((t) => t !== "get_corpus_status")) {
      const text = readFileSync(
        join(here, `schemas/${fileName(tool, "output")}.schema.json`),
        "utf8",
      );
      expect(text, tool).not.toContain("live_status");
      expect(text, tool).not.toContain("replayable");
    }
  });
});

describe("financial values stay decimal strings", () => {
  it("facts reject float values and the search scores are decimal strings", () => {
    const facts = validator(SCHEMA_IDS.mcpGetFinancialFactsOutput);
    const body = fixture("mcp-get-financial-facts-output");
    expect(facts({ ...body, facts: [{ ...body.facts[0], value: 34857 }] })).toBe(false);
    const search = validator(SCHEMA_IDS.mcpSearchFilingsOutput);
    const results = fixture("mcp-search-filings-output");
    expect(search({ ...results, results: [{ ...results.results[0], fused_score: 0.016 }] })).toBe(
      false,
    );
  });
});

describe("document metadata acceptance fields (OpenAPI 0.10.0)", () => {
  it("reader-response documentMeta takes optional accepted_at and timestamp_precision", () => {
    const valid = validator(SCHEMA_IDS.readerResponse);
    const body = fixture("reader-response");
    expect(valid(body), "unchanged fixture").toBe(true);
    const withMeta = (patch: object) => ({
      ...body,
      document: { ...body.document, meta: { ...body.document.meta, ...patch } },
    });
    expect(
      valid(withMeta({ accepted_at: "2024-03-06T21:14:09Z", timestamp_precision: "second" })),
    ).toBe(true);
    expect(valid(withMeta({ timestamp_precision: "date" }))).toBe(true);
    expect(valid(withMeta({ timestamp_precision: "approximate" }))).toBe(false);
    const yaml = readFileSync(join(here, "openapi/openapi.yaml"), "utf8");
    expect(yaml).toMatch(
      /DocumentMeta:[\s\S]*?timestamp_precision:\n\s+type: string\n\s+enum: \[date, second\]/,
    );
  });
});
