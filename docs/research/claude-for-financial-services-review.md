# Review: Claude for Financial Services (connectors, skills, plugins)

Reviewed 2026-11-10 against `main` at `270bf2f`. Sources: the academy overview
(<https://academy.claude.com/tutorials/claude-for-financial-services-overview>),
its linked tutorials, Anthropic announcements, the Apache-2.0 repository
[anthropics/financial-services](https://github.com/anthropics/financial-services)
(`6056506`, 2026-10-28), vendor documentation, and the locally synced finance
plugins. This is research, not a decision; anything adopted still needs the
ADRs named below.

**Bottom line.** The skills are reusable as Apache-2.0 *methodology*, not as
drop-in code. The vendor connectors are callable by a self-hosted backend, but
they conflict with the immutable-evidence and shared-corpus invariants unless
treated as transient, user-scoped enrichment. Most skills build DCF,
three-statement or pitch deliverables; `spec.md:86` excludes that modelling
from the MVP, and PowerPoint and Word are not export formats (`spec.md:414`).

## What the offering is

The academy page is a thin overview: Daloopa and Morningstar connectors,
Excel/Word/PowerPoint file creation, Projects per deal, and stated limits
(complex PowerPoint templates, Excel formulas needing review, input-size
limits). The substance is in `anthropics/financial-services`:

- **Vertical plugins** under `plugins/vertical-plugins/`: financial-analysis,
  investment-banking, equity-research, private-equity, fund-admin, operations.
  About 50 distinct skills, including `dcf-model`, `comps-analysis`,
  `3-statement-model`, `lbo-model`, `audit-xls`, `earnings-analysis`,
  `earnings-preview`, `initiating-coverage`, `model-update`, `ic-memo`,
  `dd-checklist`, `portfolio-monitoring`.
- **Ten agent templates** (Pitch Agent, Market Researcher, Earnings Reviewer,
  Model Builder, Valuation Reviewer, and others), deployable through Claude
  Code, Cowork, or Managed Agents (`managed-agent-cookbooks/`).
- **Partner plugins** `lseg` and `spglobal`, hard-wired to their vendors' tool
  names.
- **Twelve remote MCP servers** in
  `plugins/vertical-plugins/financial-analysis/.mcp.json`, all `type: http`
  with no auth block:

  | Server | Endpoint |
  |---|---|
  | daloopa | `https://mcp.daloopa.com/server/mcp` |
  | morningstar | `https://mcp.morningstar.com/mcp` |
  | sp-global | `https://kfinance.kensho.com/integrations/mcp` |
  | factset | `https://mcp.factset.com/mcp` |
  | moodys | `https://api.moodys.com/genai-ready-data/m1/mcp` |
  | mtnewswire | `https://vast-mcp.blueskyapi.com/mtnewswires` |
  | aiera | `https://mcp-pub.aiera.com` |
  | lseg | `https://api.analytics.lseg.com/lfa/mcp` |
  | pitchbook | `https://premium.mcp.pitchbook.com/mcp` |
  | chronograph | `https://ai.chronograph.pe/mcp` |
  | egnyte | `https://mcp-server.egnyte.com/mcp` |
  | box | `https://mcp.box.com` |

Almost everything is Markdown. The only skill-level code in the core plugin is
`dcf-model/scripts/validate_dcf.py` (stdlib imports), plus
`ib-check-deck/scripts/extract_numbers.py` and the skill-creator tooling.
`dcf-model` depends on `recalc.py` from `anthropics/skills`, which needs
LibreOffice.

## Comparison with this repository

| Capability | Here | Claude for FS |
|---|---|---|
| Point-in-time cutoffs | Enforced in retrieval, FRED vintages, derived lineage (max-of-parents) | Not addressed; `dcf-model/SKILL.md` (1,264 lines) never mentions as-of or cutoff |
| Citation integrity | Span-level, immutable, hashed; closed claim states with entailment | Cell-level source notes by instruction only |
| Financial math | Deterministic Decimal engine, typed units, cycle detection | Model-authored spreadsheet formulas |
| DCF / comps / LBO | Excluded (`spec.md:86`) | Core skills |
| Excel/Word/PowerPoint export | XLSX specified (T0510; state in the canonical ledger); Word and PowerPoint out of scope | Core output |
| Licensed data and transcripts | Absent by policy (`spec.md:84`, `:916-917`) | Twelve connectors |
| Portfolio monitoring | P1 (guidance-vs-actual, change detection) | Skill |
| Evals as release gates | Yes (retrieval gate, calibration, temporal validity) | Vendor benchmark claims only |
| Tenant isolation | RLS with negative tests | Not applicable (per-user app) |

## Can it be incorporated?

### Skill content: yes, as adapted methodology

- All sampled repositories (`financial-services`, `claude-for-financial-advisors`,
  `knowledge-work-plugins`, `skills`) are Apache-2.0. Upstream has no NOTICE
  file. Copying requires the license text, retained copyright headers, marked
  modifications, and a NOTICE entry crediting "Anthropic PBC,
  anthropics/financial-services (Apache-2.0)". Check
  `anthropics/skills/THIRD_PARTY_NOTICES.md` before copying from that repo.
- Skills may only act as authoring and orchestration aids that emit artifacts
  the existing code validates (formula AST, unit checks, cycle detection,
  citation verification). They must not output authoritative values
  (`spec.md` §8.6; `AGENTS.md` working rules).
- The most useful material: `comps-analysis`, `dcf-model` and
  `3-statement-model` methodology prose; `audit-xls` and `ib-check-deck` check
  lists; the `earnings-analysis` and `model-update` flows.

### Vendor connectors: only as transient, user-scoped enrichment

- Every connector requires the end user's own vendor entitlement and OAuth or
  key. That matches ADR-0026's user-funded model and fail-closed credentials.
- **Daloopa's [terms of use](https://daloopa.com/terms-of-use) prohibit what the
  evidence store does** (confirmed 2026-11-10): no copying or storing "any
  significant portion of the Content", no use to train AI models, and use
  only "for your internal, personal purposes" and not for third parties.
  Other vendors publish no storage or derived-data terms next to their
  connectors; assume a contract negotiation is needed for durable storage.
- Point-in-time support is thin. Daloopa exposes `filing_date`,
  `document_released_at` and a `restated` flag but no as-of query. FactSet sells
  a separate point-in-time fundamentals product; whether its MCP exposes it is
  unverified.
- There is no valid storage target today. `financial_facts` requires
  `document_version_id` and `source_span_id` (both `NOT NULL`,
  `db/migrations/0002_corpus_core.sql`), and ADR-0004 makes the public corpus
  untenanted, so licensed data cannot go there.

### Claude as a model provider: yes, already planned

- ADR-0026 (Accepted for bounded implementation) authorizes direct Anthropic
  keys as a later independently reviewed package. ADR-0012 (Proposed,
  Amendment 1) is the substitution decision and is gated on Arm A/Arm B
  evidence.
- Seam: `packages/providers/fel_providers/anthropic_structured.py`, mirroring
  `openai_structured.py`; resolver branches in
  `apps/api/app/retrieval.py` (`_resolve_generation_provider`) and
  `workers/src/fel_workers/__main__.py` (`build_structured_llm`). Credentials
  through `CredentialCipher` with `provider="anthropic"`.
- Mapping differences: top-level `system`, `msg_` response ids, undated model
  ids (the `-YYYY-MM-DD` model-id check needs a per-provider rule),
  `stop_reason` refusal/max-tokens handling, and Anthropic's structured-output
  schema subset (ADR-0015).
- Anthropic has no embeddings endpoint; embeddings stay on the existing adapter.

### MCP connector or Skills inside model calls: new ADR required

The Messages API MCP connector (`mcp_servers` + `mcp_toolset`) and the Skills
API both let the model reach external tools mid-call. That conflicts with the
adapter's single fixed endpoint and no model-initiated egress posture, and
with ADR-0026's fixed or allowlisted routing. Per the docs read by the
research agents, neither the MCP connector nor Skills is eligible for
zero-data-retention, and the caller must obtain and refresh vendor OAuth
tokens. Skills containers have no network access, so a skill cannot call a
vendor API itself.

### Locally synced plugins

Synced from claude.ai under `~/.claude/plugins/synced/`, not
`installed_plugins.json`. Only `riskmodels:fundamentals-pit` is point-in-time
(rows visible only when `filed_date <= as_of`, SEC-sourced cells as originally
reported). It is useful for cross-checking, not as evidence. The lseg,
sp-global, claude-for-financial-advisors, finance, data, small-business and
intuit-quickbooks plugins target consensus data, wealth-advisor, accounting or
SMB workflows.

## Recommended improvements, ranked

1. **Finish the extraction review loop (T0306–T0309) and connect approved facts to
   model nodes (T0404).** This is the critical path; nothing in Claude for FS
   substitutes for it. T0404 likely needs `contract-change` and an ADR.
2. **Claude structured-generation adapter** under ADR-0026's direct-key package,
   plus the Arm A/B run that ADR-0012 needs for ratification.
3. **Close the eval gaps.** None of the external benchmarks surveyed (Vals
   Finance Agent, FinanceBench, FinQA, TAT-QA, DocFinQA) scores span-level
   citations or as-of retrieval, so these are differentiators:
   - replace `evals/graders/exact_match.py` with a numeric-tolerance grader
     with scale and unit normalization;
   - add span-overlap citation precision and recall (gold quotes already exist
     in the benchmark seed);
   - extend temporal-leakage tests beyond the five trap questions (paired as-of
     queries, injected post-cutoff filings, late amendments);
   - optionally add a TAT-QA subset (CC BY 4.0). Keep FinanceBench
     (CC-BY-NC-4.0) local and uncommitted.
4. **Formula-preserving XLSX export (T0510)** that labels each value as reported,
   modeled or user-supplied. DOCX or PPTX would be new formats and need a spec
   change and ADR.
5. **Comps view on the ontology's comparability keys.** Comparability is
   enforced in code here, where Claude for FS leaves it to the model. New scope
   beyond spec §4, so it needs a spec amendment and ADR.
6. **Vendor-data ADR before any connector work**, covering a tenant-scoped
   `vendor_facts` table (next migration `0012_*`), a non-span citation shape in
   `packages/contracts`, licensing and retention (`spec.md:915-921`), and source
   clocks (ADR-0031).

## Verification status

Checked directly in this review: `spec.md:84,86,916-917`; ADR status lines for
0012, 0026, 0029 and 0031; the `financial_facts` constraints; the upstream
repository's license, skill list and `.mcp.json` endpoints; the Daloopa terms
clauses quoted above.

Reported by research agents but not re-checked:

- vendor endpoints outside `anthropics/financial-services` and per-vendor auth;
  FactSet appears as both `/mcp` and `/content/v1` in different sources;
- Anthropic API details: MCP connector beta headers (`mcp-client-2025-11-20`,
  `mcp-client-2026-09-15`), the Skills API no longer needing a beta header,
  the code-execution tool version (sources conflict), and `claude-fable-5-2`
  being the current Fable model;
- benchmark figures (Vals Finance Agent leaderboard values).
