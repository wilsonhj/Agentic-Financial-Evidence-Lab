-- Issue #405, ADR-0034 Amendment 2: narrowly scoped worker backfill grants.
-- Actual-role writes pin both the new permissions and the unchanged evidence
-- boundaries. These are COLUMN privileges, not row filters: #393 must exclude
-- COMPANYFACTS and verify publication metadata in its backfill implementation.

\set ON_ERROR_STOP on

BEGIN;

\ir _helpers.sql

-- SECURITY INVOKER (the default): every dynamic UPDATE runs as the caller.
-- Check each column separately so a stray single-column grant cannot hide
-- behind another denied column in a multi-column UPDATE.
CREATE FUNCTION pg_temp.expect_backfill_denied() RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    col record;
BEGIN
    FOR col IN
        SELECT c.relname, a.attname
        FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
        WHERE (a.attrelid = 'documents'::regclass AND a.attname IN
               ('accepted_at', 'public_at', 'public_at_basis', 'timestamp_precision'))
           OR (a.attrelid = 'financial_facts'::regclass AND a.attname = 'restates')
    LOOP
        PERFORM pg_temp.expect_rejection(
            format('%I UPDATE %I.%I', current_user, col.relname, col.attname),
            format('UPDATE public.%I SET %I = %I', col.relname, col.attname, col.attname),
            ARRAY['42501']);
    END LOOP;
END
$$;

-- Seed through existing worker INSERT privileges, not as the migration owner.
SET LOCAL ROLE fel_worker;

INSERT INTO documents (
    id, entity_id, accession, source_url, content_hash, storage_key,
    published_at, filed_at
) VALUES (
    '00000000-0000-0000-0000-000000001301',
    '00000000-0000-0000-0000-000000001300', 'backfill-13',
    'https://example.test/backfill-13', 'sha256:' || repeat('13', 32),
    'raw/backfill-13', '2024-03-06T00:00:00Z', '2024-03-06T00:00:00Z'
);
INSERT INTO document_versions (
    id, document_id, parser_version, normalizer_version, canonical_text_key
) VALUES (
    '00000000-0000-0000-0000-000000001302',
    '00000000-0000-0000-0000-000000001301', 'p13', 'n13', 'text/backfill-13'
);
INSERT INTO sections (
    id, document_version_id, heading, heading_path, ord, start_char, end_char
) VALUES (
    '00000000-0000-0000-0000-000000001303',
    '00000000-0000-0000-0000-000000001302', 'Revenue', ARRAY['Revenue'], 0, 0, 20
);
INSERT INTO source_spans (
    id, document_version_id, section_id, start_char, end_char, text_hash
) VALUES (
    '00000000-0000-0000-0000-000000001304',
    '00000000-0000-0000-0000-000000001302',
    '00000000-0000-0000-0000-000000001303', 0, 20, 'sha256:' || repeat('14', 32)
);
INSERT INTO financial_facts (
    id, entity_id, document_version_id, concept, value, unit, period_type,
    period_start, period_end, source_span_id, fact_key
) VALUES
    ('00000000-0000-0000-0000-000000001305',
     '00000000-0000-0000-0000-000000001300',
     '00000000-0000-0000-0000-000000001302', 'Revenues', '100', 'USD', 'duration',
     '2024-01-01', '2024-03-31', '00000000-0000-0000-0000-000000001304', 'original-13'),
    ('00000000-0000-0000-0000-000000001306',
     '00000000-0000-0000-0000-000000001300',
     '00000000-0000-0000-0000-000000001302', 'Revenues', '110', 'USD', 'duration',
     '2024-01-01', '2024-03-31', '00000000-0000-0000-0000-000000001304', 'amended-13');

-- This first new write fails with 42501 before 0013 is applied. All four
-- publication columns must change together to satisfy 0012's existing CHECKs.
UPDATE documents
SET accepted_at = '2024-03-05T23:00:00Z', public_at = '2024-03-06T11:00:00Z',
    public_at_basis = 'next_session_open', timestamp_precision = 'second'
WHERE id = '00000000-0000-0000-0000-000000001301';
UPDATE financial_facts SET restates = '00000000-0000-0000-0000-000000001305'
WHERE id = '00000000-0000-0000-0000-000000001306';

DO $$
BEGIN
    IF current_user <> 'fel_worker' THEN
        RAISE EXCEPTION 'not ok - writes did not execute as fel_worker';
    END IF;
    IF (SELECT ROW(accepted_at, public_at, public_at_basis, timestamp_precision)
        FROM documents WHERE id = '00000000-0000-0000-0000-000000001301')
       IS DISTINCT FROM ROW('2024-03-05T23:00:00Z'::timestamptz,
                            '2024-03-06T11:00:00Z'::timestamptz,
                            'next_session_open'::text, 'second'::text) THEN
        RAISE EXCEPTION 'not ok - worker publication backfill did not persist';
    END IF;
    IF (SELECT restates FROM financial_facts
        WHERE id = '00000000-0000-0000-0000-000000001306')
       IS DISTINCT FROM '00000000-0000-0000-0000-000000001305'::uuid THEN
        RAISE EXCEPTION 'not ok - worker restatement repair did not persist';
    END IF;
    RAISE NOTICE 'ok - fel_worker inserts evidence and updates publication metadata/restates';
END
$$;

-- Permission to write these columns does not bypass data constraints.
SELECT pg_temp.expect_rejection('worker cannot clear one publication instant',
    $sql$UPDATE documents SET accepted_at = NULL
         WHERE id = '00000000-0000-0000-0000-000000001301'$sql$, ARRAY['23514']);
SELECT pg_temp.expect_rejection('worker cannot mislabel known timestamps',
    $sql$UPDATE documents SET timestamp_precision = 'date'
         WHERE id = '00000000-0000-0000-0000-000000001301'$sql$, ARRAY['23514']);
SELECT pg_temp.expect_rejection('worker cannot link a missing restated fact',
    $sql$UPDATE financial_facts SET restates = '00000000-0000-0000-0000-0000000013ff'
         WHERE id = '00000000-0000-0000-0000-000000001306'$sql$, ARRAY['23503']);

-- Every other column of the two changed tables must still be denied. A
-- no-op assignment is intentional: even valid, unchanged values need UPDATE.
DO $$
DECLARE
    col record;
BEGIN
    FOR col IN
        SELECT c.relname, a.attname
        FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
        WHERE a.attrelid IN ('documents'::regclass, 'financial_facts'::regclass)
          AND a.attnum > 0 AND NOT a.attisdropped
          AND NOT (c.relname = 'documents' AND a.attname IN
                   ('accepted_at', 'public_at', 'public_at_basis', 'timestamp_precision'))
          AND NOT (c.relname = 'financial_facts' AND a.attname = 'restates')
        ORDER BY c.relname, a.attnum
    LOOP
        PERFORM pg_temp.expect_rejection(
            format('worker UPDATE %I.%I', col.relname, col.attname),
            format('UPDATE public.%I SET %I = %I', col.relname, col.attname, col.attname),
            ARRAY['42501']);
    END LOOP;
END
$$;

-- A combined statement cannot smuggle a forbidden column alongside an allowed one.
SELECT pg_temp.expect_rejection('worker mixed document update',
    $sql$UPDATE documents SET public_at = public_at, content_hash = content_hash$sql$,
    ARRAY['42501']);
SELECT pg_temp.expect_rejection('worker mixed fact update',
    $sql$UPDATE financial_facts SET restates = restates, value = value$sql$, ARRAY['42501']);
SELECT pg_temp.expect_rejection('worker cannot rewrite canonical text',
    'UPDATE document_versions SET canonical_text_key = canonical_text_key', ARRAY['42501']);
SELECT pg_temp.expect_rejection('worker cannot rewrite evidence hashes',
    'UPDATE source_spans SET text_hash = text_hash', ARRAY['42501']);
SELECT pg_temp.expect_rejection('worker cannot delete documents',
    'DELETE FROM documents', ARRAY['42501']);
SELECT pg_temp.expect_rejection('worker cannot delete facts',
    'DELETE FROM financial_facts', ARRAY['42501']);

RESET ROLE;

-- Check the effective ACL, including inherited/PUBLIC privileges. Do not
-- infer an across-the-board worker UPDATE denial: jobs, ingestion_runs and
-- other runtime tables legitimately retain their earlier UPDATE privileges.
DO $$
DECLARE
    col record;
    expected boolean;
BEGIN
    IF has_table_privilege('fel_worker', 'documents', 'UPDATE')
       OR has_table_privilege('fel_worker', 'financial_facts', 'UPDATE') THEN
        RAISE EXCEPTION 'not ok - worker received table-level UPDATE';
    END IF;
    FOR col IN
        SELECT c.oid, c.relname, a.attname
        FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
        WHERE a.attrelid IN ('documents'::regclass, 'financial_facts'::regclass)
          AND a.attnum > 0 AND NOT a.attisdropped
    LOOP
        expected := (col.relname = 'documents' AND col.attname IN
                     ('accepted_at', 'public_at', 'public_at_basis', 'timestamp_precision'))
                    OR (col.relname = 'financial_facts' AND col.attname = 'restates');
        IF has_column_privilege('fel_worker', col.oid, col.attname, 'UPDATE')
           IS DISTINCT FROM expected THEN
            RAISE EXCEPTION 'not ok - worker UPDATE on %.% differs from allowlist',
                col.relname, col.attname;
        END IF;
    END LOOP;
    RAISE NOTICE 'ok - effective worker UPDATE is exactly the five authorized columns';
END
$$;

-- Neither the tenant request role nor the anonymous public role inherits the
-- new writes. These assertions execute as each role, not as the schema owner.
SET LOCAL ROLE fel_app;
SELECT pg_temp.expect_backfill_denied();
RESET ROLE;

SET LOCAL ROLE fel_public_read;
DO $$
BEGIN
    IF (SELECT count(*) FROM documents
        WHERE id = '00000000-0000-0000-0000-000000001301') <> 1
       OR (SELECT count(*) FROM financial_facts
           WHERE document_version_id = '00000000-0000-0000-0000-000000001302') <> 2 THEN
        RAISE EXCEPTION 'not ok - public corpus SELECT was lost';
    END IF;
    RAISE NOTICE 'ok - public role retains corpus reads';
END
$$;
SELECT pg_temp.expect_backfill_denied();
SELECT pg_temp.expect_rejection('public cannot read tenant workspaces',
    'SELECT id FROM workspaces LIMIT 0', ARRAY['42501']);
SELECT pg_temp.expect_rejection('public cannot read tenant organizations',
    'SELECT id FROM organizations LIMIT 0', ARRAY['42501']);
SELECT pg_temp.expect_rejection('public cannot write documents',
    'DELETE FROM documents', ARRAY['42501']);
RESET ROLE;

ROLLBACK;
