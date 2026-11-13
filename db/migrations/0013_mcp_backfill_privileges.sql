-- Issue #405, ADR-0034 Amendment 2: allow #393's worker-role backfill to
-- record verified SEC publication metadata and repair restatement links.
-- Correct forward from 0012; do not edit an applied migration.
--
-- These column grants leave raw source bytes, hashes, dates, canonical text,
-- financial values and every other existing privilege unchanged. They are
-- NOT row restrictions: #393 must exclude COMPANYFACTS, validate pinned
-- metadata and constrain repair targets in its implementation and tests.
-- Neither fel_app nor fel_public_read receives any new privilege.
-- Harness: tests/0013_mcp_backfill_privileges.test.sql.

GRANT UPDATE (accepted_at, public_at, public_at_basis, timestamp_precision)
    ON documents TO fel_worker;
GRANT UPDATE (restates) ON financial_facts TO fel_worker;
