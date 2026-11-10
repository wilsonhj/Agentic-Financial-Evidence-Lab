export type { components, paths, operations } from "./generated/api";

/** Frozen schema registry: name -> versioned $id (see VERSIONING.md). */
export const SCHEMA_IDS = {
  extractionCandidateFields: "https://contracts.fel.dev/schemas/extraction-candidate-fields/v1",
  extractionReviewCommand: "https://contracts.fel.dev/schemas/extraction-review-command/v1",
  extractionReviewResult: "https://contracts.fel.dev/schemas/extraction-review-result/v1",
  extractionConflict: "https://contracts.fel.dev/schemas/extraction-conflict/v1",
  extractionValidationContext: "https://contracts.fel.dev/schemas/extraction-validation-context/v1",
  extractionEventPage: "https://contracts.fel.dev/schemas/extraction-event-page/v1",
  retrievalEventPage: "https://contracts.fel.dev/schemas/retrieval-event-page/v1",
  documentVersionReference: "https://contracts.fel.dev/schemas/document-version-reference/v1",
  sourceSpan: "https://contracts.fel.dev/schemas/source-span/v1",
  financialFact: "https://contracts.fel.dev/schemas/financial-fact/v1",
  claim: "https://contracts.fel.dev/schemas/claim/v1",
  claimsOutput: "https://contracts.fel.dev/schemas/claims-output/v1",
  citation: "https://contracts.fel.dev/schemas/citation/v1",
  jobEnvelope: "https://contracts.fel.dev/schemas/job-envelope/v1",
  tenantContext: "https://contracts.fel.dev/schemas/tenant-context/v1",
  error: "https://contracts.fel.dev/schemas/error/v1",
  readerResponse: "https://contracts.fel.dev/schemas/reader-response/v1",
  queryPlan: "https://contracts.fel.dev/schemas/query-plan/v1",
  retrievalEvent: "https://contracts.fel.dev/schemas/retrieval-event/v1",
  retrievalTrace: "https://contracts.fel.dev/schemas/retrieval-trace/v1",
  evidenceFeedback: "https://contracts.fel.dev/schemas/evidence-feedback/v1",
  extractionEvent: "https://contracts.fel.dev/schemas/extraction-event/v1",
  extractionPayload: "https://contracts.fel.dev/schemas/extraction-payload/v1",
  mcpEvidenceContext: "https://contracts.fel.dev/schemas/mcp-evidence-context/v1",
  mcpCitation: "https://contracts.fel.dev/schemas/mcp-citation/v1",
  mcpVerificationReport: "https://contracts.fel.dev/schemas/mcp-verification-report/v1",
  mcpError: "https://contracts.fel.dev/schemas/mcp-error/v1",
  mcpResolveCompanyInput: "https://contracts.fel.dev/schemas/mcp-resolve-company-input/v1",
  mcpResolveCompanyOutput: "https://contracts.fel.dev/schemas/mcp-resolve-company-output/v1",
  mcpListFilingsInput: "https://contracts.fel.dev/schemas/mcp-list-filings-input/v1",
  mcpListFilingsOutput: "https://contracts.fel.dev/schemas/mcp-list-filings-output/v1",
  mcpSearchFilingsInput: "https://contracts.fel.dev/schemas/mcp-search-filings-input/v1",
  mcpSearchFilingsOutput: "https://contracts.fel.dev/schemas/mcp-search-filings-output/v1",
  mcpReadFilingInput: "https://contracts.fel.dev/schemas/mcp-read-filing-input/v1",
  mcpReadFilingOutput: "https://contracts.fel.dev/schemas/mcp-read-filing-output/v1",
  mcpGetCitationInput: "https://contracts.fel.dev/schemas/mcp-get-citation-input/v1",
  mcpGetCitationOutput: "https://contracts.fel.dev/schemas/mcp-get-citation-output/v1",
  mcpGetFinancialFactsInput: "https://contracts.fel.dev/schemas/mcp-get-financial-facts-input/v1",
  mcpGetFinancialFactsOutput: "https://contracts.fel.dev/schemas/mcp-get-financial-facts-output/v1",
  mcpVerifyClaimInput: "https://contracts.fel.dev/schemas/mcp-verify-claim-input/v1",
  mcpVerifyClaimOutput: "https://contracts.fel.dev/schemas/mcp-verify-claim-output/v1",
  mcpGetCorpusStatusInput: "https://contracts.fel.dev/schemas/mcp-get-corpus-status-input/v1",
  mcpGetCorpusStatusOutput: "https://contracts.fel.dev/schemas/mcp-get-corpus-status-output/v1",
} as const;

/** MCP evidence tools (ADR-0034, design contract §7): tool name -> input/output schema $id.
 * Order is the published tool order. Output schemas $ref the mcp-* schemas by canonical $id,
 * so a server must bundle them before sending an outputSchema to clients.
 */
export const MCP_TOOL_SCHEMAS = {
  resolve_company: {
    input: SCHEMA_IDS.mcpResolveCompanyInput,
    output: SCHEMA_IDS.mcpResolveCompanyOutput,
  },
  list_filings: { input: SCHEMA_IDS.mcpListFilingsInput, output: SCHEMA_IDS.mcpListFilingsOutput },
  search_filings: {
    input: SCHEMA_IDS.mcpSearchFilingsInput,
    output: SCHEMA_IDS.mcpSearchFilingsOutput,
  },
  read_filing: { input: SCHEMA_IDS.mcpReadFilingInput, output: SCHEMA_IDS.mcpReadFilingOutput },
  get_citation: { input: SCHEMA_IDS.mcpGetCitationInput, output: SCHEMA_IDS.mcpGetCitationOutput },
  get_financial_facts: {
    input: SCHEMA_IDS.mcpGetFinancialFactsInput,
    output: SCHEMA_IDS.mcpGetFinancialFactsOutput,
  },
  verify_claim: { input: SCHEMA_IDS.mcpVerifyClaimInput, output: SCHEMA_IDS.mcpVerifyClaimOutput },
  get_corpus_status: {
    input: SCHEMA_IDS.mcpGetCorpusStatusInput,
    output: SCHEMA_IDS.mcpGetCorpusStatusOutput,
  },
} as const;

export const CONTRACT_VERSION = "0.10.0" as const;

/** Relative file references resolved against canonical $id values (ADR-0024).
 * Register these aliases alongside SCHEMA_IDS for offline JSON Schema validation.
 */
export const SCHEMA_REFERENCE_ALIASES = {
  "https://contracts.fel.dev/schemas/extraction-review-command/extraction-payload.schema.json":
    SCHEMA_IDS.extractionPayload,
  "https://contracts.fel.dev/schemas/extraction-event-page/extraction-event.schema.json":
    SCHEMA_IDS.extractionEvent,
} as const;
