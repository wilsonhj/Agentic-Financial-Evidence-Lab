-- Harness for 0012_acceptance_time_and_public_read.sql (issue #392,
-- ADR-0034 decisions 2 and 4 with Amendment 1).
--
-- Three things are pinned here:
-- 1. documents.accepted_at / public_at / public_at_basis /
--    timestamp_precision: defaults, every CHECK that ties them together, and
--    the (entity_id, public_at) index.
-- 2. fel_guard_candidate on GREATEST(COALESCE(public_at, published_at),
--    published_at): a same-day filing made public after the cutoff is
--    hidden; an after-hours filing (accepted the evening before its filing
--    date) is hidden until 06:00 ET on the filing date and visible from then,
--    across a weekend and a daylight-saving change; a NULL public_at falls
--    back to published_at in both directions; and a row whose public_at
--    precedes published_at is still held to published_at (never weaker than
--    the 0003 rule). Candidates are inserted as fel_app, the role that writes
--    them in production.
-- 3. fel_public_read: exactly SELECT on the ten allowlisted untenanted
--    tables, nothing on any other relation or sequence, no role attributes or
--    memberships, and each denial proven by an actual statement raising 42501
--    under SET LOCAL ROLE.
--
-- Id block 0x12xx keeps clear of the other harnesses.

\set ON_ERROR_STOP on

BEGIN;

\ir _helpers.sql

-- ---------------------------------------------------------------------------
-- 1. Columns, constraints and index
-- ---------------------------------------------------------------------------

INSERT INTO documents (
    id, entity_id, accession, source_url, content_hash, storage_key,
    published_at, accepted_at, public_at, public_at_basis, timestamp_precision
) VALUES
    -- D1 same day: filing date 2024-03-06, accepted 15:00 EST (20:00Z),
    -- public at acceptance.
    ('00000000-0000-0000-0000-000000001201', '00000000-0000-0000-0000-000000001200',
     'acc-12-same-day', 'https://example.test/12/1',
     'sha256:1201120112011201120112011201120112011201120112011201120112011201', 'raw/1201',
     '2024-03-06T00:00:00Z', '2024-03-06T20:00:00Z', '2024-03-06T20:00:00Z',
     'acceptance', 'second'),
    -- D3 after hours: accepted 18:00 EST on 03-05 (23:00Z), filing date
    -- 03-06, so accepted_at precedes published_at. Public at 06:00 EST on
    -- 03-06 (11:00Z).
    ('00000000-0000-0000-0000-000000001203', '00000000-0000-0000-0000-000000001200',
     'acc-12-after-hours', 'https://example.test/12/3',
     'sha256:1203120312031203120312031203120312031203120312031203120312031203', 'raw/1203',
     '2024-03-06T00:00:00Z', '2024-03-05T23:00:00Z', '2024-03-06T11:00:00Z',
     'next_session_open', 'second'),
    -- D4 adversarial: public_at (22:00Z on 03-05) precedes published_at
    -- (03-06). The constraints allow the row; the derivation rule would not
    -- produce it. The guard must still hold it to published_at.
    ('00000000-0000-0000-0000-000000001204', '00000000-0000-0000-0000-000000001200',
     'acc-12-early-public', 'https://example.test/12/4',
     'sha256:1204120412041204120412041204120412041204120412041204120412041204', 'raw/1204',
     '2024-03-06T00:00:00Z', '2024-03-05T22:00:00Z', '2024-03-05T22:00:00Z',
     'acceptance', 'second'),
    -- D5 weekend after hours: accepted Friday 2024-03-08 18:30 EST (23:30Z),
    -- filing date Monday 03-11. DST began 03-10, so 06:00 EDT is 10:00Z.
    ('00000000-0000-0000-0000-000000001205', '00000000-0000-0000-0000-000000001200',
     'acc-12-weekend', 'https://example.test/12/5',
     'sha256:1205120512051205120512051205120512051205120512051205120512051205', 'raw/1205',
     '2024-03-11T00:00:00Z', '2024-03-08T23:30:00Z', '2024-03-11T10:00:00Z',
     'next_session_open', 'second');
-- D2 date-only: no acceptance or publication time; the defaults must apply.
INSERT INTO documents (
    id, entity_id, accession, source_url, content_hash, storage_key, published_at
) VALUES
    ('00000000-0000-0000-0000-000000001202', '00000000-0000-0000-0000-000000001200',
     'acc-12-date-only', 'https://example.test/12/2',
     'sha256:1202120212021202120212021202120212021202120212021202120212021202', 'raw/1202',
     '2024-03-06T00:00:00Z');

DO $$
BEGIN
    IF (SELECT ROW(accepted_at, public_at, public_at_basis, timestamp_precision)
        FROM documents WHERE id = '00000000-0000-0000-0000-000000001202')
       IS DISTINCT FROM ROW(NULL::timestamptz, NULL::timestamptz, NULL::text, 'date'::text) THEN
        RAISE EXCEPTION 'not ok - legacy insert did not default to (NULL, NULL, NULL, date)';
    END IF;
    RAISE NOTICE 'ok - legacy insert defaults to NULL instants, NULL basis, precision date';

    IF NOT EXISTS (
        SELECT 1
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        WHERE c.relname = 'documents_entity_public_idx'
          AND i.indrelid = 'documents'::regclass
          AND (SELECT array_agg(a.attname::text ORDER BY k.ord)
               FROM unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord)
               JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum)
              = ARRAY['entity_id', 'public_at']
    ) THEN
        RAISE EXCEPTION 'not ok - (entity_id, public_at) index missing';
    END IF;
    IF to_regclass('documents_entity_accepted_idx') IS NOT NULL THEN
        RAISE EXCEPTION 'not ok - superseded (entity_id, accepted_at) index exists';
    END IF;
    RAISE NOTICE 'ok - documents_entity_public_idx covers (entity_id, public_at)';
END
$$;

-- Each case inserts one document with the given (accepted_at, public_at,
-- public_at_basis, timestamp_precision) and expects the CHECK to refuse it.
CREATE FUNCTION pg_temp.document_sql(
    n integer, accepted text, pub text, basis text, precision_ text
) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT format(
        'INSERT INTO documents (id, entity_id, accession, source_url, content_hash, '
        'storage_key, published_at, accepted_at, public_at, public_at_basis, '
        'timestamp_precision) VALUES (%L, %L, %L, %L, %L, %L, %L, %L::timestamptz, '
        '%L::timestamptz, %L, %L)',
        format('00000000-0000-0000-0000-0000000012%s', 10 + n),
        '00000000-0000-0000-0000-000000001200',
        format('acc-12-bad-%s', n),
        format('https://example.test/12/b%s', n),
        'sha256:' || repeat(lpad(n::text, 2, '0'), 32),
        format('raw/b%s', n),
        '2024-03-06T00:00:00Z', accepted, pub, basis, precision_)
$$;

SELECT pg_temp.expect_rejection('second precision without any instant',
    pg_temp.document_sql(1, NULL, NULL, NULL, 'second'), ARRAY['23514']);
SELECT pg_temp.expect_rejection('instants labeled date precision',
    pg_temp.document_sql(2, '2024-03-06T20:00:00Z', '2024-03-06T20:00:00Z', 'acceptance', 'date'),
    ARRAY['23514']);
SELECT pg_temp.expect_rejection('unknown timestamp precision',
    -- NULL instants, so only the enum CHECK (not the precision pair) can refuse it.
    pg_temp.document_sql(3, NULL, NULL, NULL, 'approximate'),
    ARRAY['23514']);
SELECT pg_temp.expect_rejection('null timestamp precision',
    pg_temp.document_sql(4, NULL, NULL, NULL, NULL), ARRAY['23502']);
SELECT pg_temp.expect_rejection('accepted_at without public_at',
    pg_temp.document_sql(5, '2024-03-06T20:00:00Z', NULL, NULL, 'second'), ARRAY['23514']);
SELECT pg_temp.expect_rejection('public_at without accepted_at',
    pg_temp.document_sql(6, NULL, '2024-03-06T20:00:00Z', 'acceptance', 'second'), ARRAY['23514']);
SELECT pg_temp.expect_rejection('instants without a basis',
    pg_temp.document_sql(7, '2024-03-06T20:00:00Z', '2024-03-06T20:00:00Z', NULL, 'second'),
    ARRAY['23514']);
SELECT pg_temp.expect_rejection('basis without instants',
    pg_temp.document_sql(8, NULL, NULL, 'acceptance', 'date'), ARRAY['23514']);
SELECT pg_temp.expect_rejection('unknown public_at_basis',
    -- public_at > accepted_at, so only the enum CHECK (not consistency) can refuse it.
    pg_temp.document_sql(9, '2024-03-05T23:00:00Z', '2024-03-06T11:00:00Z', 'dissemination', 'second'),
    ARRAY['23514']);
SELECT pg_temp.expect_rejection('public_at before accepted_at',
    pg_temp.document_sql(10, '2024-03-06T20:00:00Z', '2024-03-06T19:59:59Z', 'next_session_open', 'second'),
    ARRAY['23514']);
SELECT pg_temp.expect_rejection('acceptance basis with public_at after accepted_at',
    pg_temp.document_sql(11, '2024-03-05T23:00:00Z', '2024-03-06T11:00:00Z', 'acceptance', 'second'),
    ARRAY['23514']);
SELECT pg_temp.expect_rejection('next_session_open basis with public_at = accepted_at',
    pg_temp.document_sql(12, '2024-03-06T20:00:00Z', '2024-03-06T20:00:00Z', 'next_session_open', 'second'),
    ARRAY['23514']);

-- ---------------------------------------------------------------------------
-- 2. fel_guard_candidate on publication time
-- ---------------------------------------------------------------------------

INSERT INTO organizations (id, name)
VALUES ('00000000-0000-0000-0000-000000001221', 'Publication Org');
INSERT INTO memberships (org_id, user_id, role)
VALUES ('00000000-0000-0000-0000-000000001221', '00000000-0000-0000-0000-000000001222', 'owner');
INSERT INTO workspaces (id, org_id, name, entity_id, base_currency, fiscal_calendar, as_of)
VALUES ('00000000-0000-0000-0000-000000001223', '00000000-0000-0000-0000-000000001221',
        'Publication WS', '00000000-0000-0000-0000-000000001200', 'USD', 'calendar',
        '2030-01-01T00:00:00Z');

-- One parsed version, section, span and retrieval item per document n = 1..5.
INSERT INTO document_versions (id, document_id, parser_version, normalizer_version,
                               canonical_text_key)
SELECT format('00000000-0000-0000-0000-00000000123%s', n)::uuid,
       format('00000000-0000-0000-0000-00000000120%s', n)::uuid,
       'p1', 'n1', format('text/123%s', n)
FROM generate_series(1, 5) AS n;
INSERT INTO sections (id, document_version_id, heading, heading_path, ord, start_char, end_char)
SELECT format('00000000-0000-0000-0000-00000000124%s', n)::uuid,
       format('00000000-0000-0000-0000-00000000123%s', n)::uuid,
       'S', ARRAY['S'], 0, 0, 10
FROM generate_series(1, 5) AS n;
INSERT INTO source_spans (id, document_version_id, section_id, start_char, end_char, text_hash)
SELECT format('00000000-0000-0000-0000-00000000125%s', n)::uuid,
       format('00000000-0000-0000-0000-00000000123%s', n)::uuid,
       format('00000000-0000-0000-0000-00000000124%s', n)::uuid,
       0, 10, 'sha256:' || repeat(format('125%s', n), 16)
FROM generate_series(1, 5) AS n;
INSERT INTO corpus_versions (id, label, status, is_active, published_at)
VALUES ('00000000-0000-0000-0000-000000001260', 'Publication corpus', 'superseded', false, now());
INSERT INTO corpus_version_documents (corpus_version_id, document_version_id)
SELECT '00000000-0000-0000-0000-000000001260',
       format('00000000-0000-0000-0000-00000000123%s', n)::uuid
FROM generate_series(1, 5) AS n;
-- A keyword-only index version (ADR-0034 decision 6): sentinel provider.
INSERT INTO retrieval_index_versions (id, corpus_version_id, chunker_version, config_hash,
                                      embedding_provider, embedding_model)
VALUES ('00000000-0000-0000-0000-000000001261', '00000000-0000-0000-0000-000000001260', 'v1',
        'sha256:1261126112611261126112611261126112611261126112611261126112611261',
        'none', 'none');
UPDATE retrieval_index_versions SET status = 'building'
    WHERE id = '00000000-0000-0000-0000-000000001261';
INSERT INTO retrieval_items (id, index_version_id, kind, entity_id, document_id,
                             document_version_id, section_id, source_span_id, content,
                             content_sha256, start_char, end_char, token_count)
SELECT format('00000000-0000-0000-0000-00000000127%s', n)::uuid,
       '00000000-0000-0000-0000-000000001261', 'passage',
       '00000000-0000-0000-0000-000000001200',
       format('00000000-0000-0000-0000-00000000120%s', n)::uuid,
       format('00000000-0000-0000-0000-00000000123%s', n)::uuid,
       format('00000000-0000-0000-0000-00000000124%s', n)::uuid,
       format('00000000-0000-0000-0000-00000000125%s', n)::uuid,
       format('passage %s', n), 'sha256:' || repeat(format('127%s', n), 16), 0, 10, 2
FROM generate_series(1, 5) AS n;
UPDATE retrieval_index_versions SET status = 'ready', published_at = now()
    WHERE id = '00000000-0000-0000-0000-000000001261';

-- One query (and run) per cutoff:
--   q1 09:00 EST 03-06   q2 05:00 EST 03-06 (after the filing-date midnight,
--   before EDGAR opens)  q3 18:30 EST 03-05   q4 16:00 EST 03-06
--   q5 Saturday 03-09    q6 05:59:59 EDT 03-11   q7 06:00 EDT 03-11
CREATE TEMP TABLE cutoffs (n integer PRIMARY KEY, cutoff timestamptz NOT NULL);
INSERT INTO cutoffs VALUES
    (1, '2024-03-06T14:00:00Z'), (2, '2024-03-06T10:00:00Z'),
    (3, '2024-03-05T23:30:00Z'), (4, '2024-03-06T21:00:00Z'),
    (5, '2024-03-09T15:00:00Z'), (6, '2024-03-11T09:59:59Z'),
    (7, '2024-03-11T10:00:00Z');
INSERT INTO queries (id, org_id, workspace_id, created_by, question, effective_as_of,
                     corpus_version_id, index_version_id, plan, planner_version)
SELECT format('00000000-0000-0000-0000-00000000128%s', n)::uuid,
       '00000000-0000-0000-0000-000000001221', '00000000-0000-0000-0000-000000001223',
       '00000000-0000-0000-0000-000000001222', format('cutoff %s', n), cutoff,
       '00000000-0000-0000-0000-000000001260', '00000000-0000-0000-0000-000000001261',
       '{}'::jsonb, 'planner-v1'
FROM cutoffs;
INSERT INTO retrieval_runs (id, org_id, query_id, mode, config_hash, embedding_provider,
                            embedding_model, planner_version)
SELECT format('00000000-0000-0000-0000-00000000129%s', n)::uuid,
       '00000000-0000-0000-0000-000000001221',
       format('00000000-0000-0000-0000-00000000128%s', n)::uuid,
       'execute',
       'sha256:1290129012901290129012901290129012901290129012901290129012901290',
       'none', 'none', 'planner-v1'
FROM cutoffs;
UPDATE retrieval_runs SET status = 'planning'
    WHERE org_id = '00000000-0000-0000-0000-000000001221';
UPDATE retrieval_runs SET status = 'retrieving'
    WHERE org_id = '00000000-0000-0000-0000-000000001221';

-- Inserts one lexical candidate (run n, item m); id encodes both.
CREATE FUNCTION pg_temp.candidate_sql(run_n integer, item_m integer) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT format(
        'INSERT INTO retrieval_candidates (id, org_id, run_id, retrieval_item_id, lane, '
        'variant_index, lane_rank, raw_score, rrf_contribution, fused_score, accepted, '
        'timing_ms) VALUES (%L, %L, %L, %L, ''lexical'', 0, %s, ''1'', ''0.01'', ''0.01'', '
        'false, 1)',
        format('12000000-0000-0000-0000-0000000000%s%s', run_n, item_m),
        '00000000-0000-0000-0000-000000001221',
        format('00000000-0000-0000-0000-00000000129%s', run_n),
        format('00000000-0000-0000-0000-00000000127%s', item_m),
        item_m)
$$;

SET LOCAL ROLE fel_app;
SELECT set_config('request.jwt.claims',
                  '{"org_id":"00000000-0000-0000-0000-000000001221"}', true);

-- q1, 09:00 EST: the same-day filing made public at 15:00 EST is hidden.
-- Under the 0003 rule (published_at midnight <= cutoff) it was admitted.
SELECT pg_temp.expect_rejection('same-day filing public after the cutoff',
    pg_temp.candidate_sql(1, 1), ARRAY['P0001']);
DO $$ BEGIN EXECUTE pg_temp.candidate_sql(1, 2);
    RAISE NOTICE 'ok - NULL public_at falls back to published_at (admitted)'; END $$;
DO $$ BEGIN EXECUTE pg_temp.candidate_sql(1, 3);
    RAISE NOTICE 'ok - after-hours filing visible after 06:00 ET on its filing date'; END $$;

-- q2, 05:00 EST on the filing date: the after-hours filing was accepted the
-- evening before and its filing-date midnight has passed, but EDGAR has not
-- opened. Acceptance-time and filing-date rules would both admit it.
SELECT pg_temp.expect_rejection('after-hours filing before EDGAR opens on its filing date',
    pg_temp.candidate_sql(2, 3), ARRAY['P0001']);
DO $$ BEGIN EXECUTE pg_temp.candidate_sql(2, 2);
    RAISE NOTICE 'ok - date-only filing admitted after its filing-date midnight'; END $$;

-- q3, 18:30 EST the evening before: after acceptance, before the filing date.
SELECT pg_temp.expect_rejection('after-hours filing between acceptance and filing date',
    pg_temp.candidate_sql(3, 3), ARRAY['P0001']);
SELECT pg_temp.expect_rejection('NULL public_at falls back to published_at (rejected)',
    pg_temp.candidate_sql(3, 2), ARRAY['P0001']);
SELECT pg_temp.expect_rejection('public_at before published_at is held to published_at (never weaker)',
    pg_temp.candidate_sql(3, 4), ARRAY['P0001']);

-- q4, 16:00 EST: the same-day filing is public; D4 is past both instants.
DO $$ BEGIN EXECUTE pg_temp.candidate_sql(4, 1);
    RAISE NOTICE 'ok - same-day filing public before the cutoff is admitted'; END $$;
DO $$ BEGIN EXECUTE pg_temp.candidate_sql(4, 4);
    RAISE NOTICE 'ok - early-public row admitted once published_at passes'; END $$;

-- q5-q7: the Friday-evening filing stays hidden all weekend and until 06:00
-- EDT Monday (after the 03-10 daylight-saving change), inclusive.
SELECT pg_temp.expect_rejection('weekend: Friday after-hours filing hidden on Saturday',
    pg_temp.candidate_sql(5, 5), ARRAY['P0001']);
SELECT pg_temp.expect_rejection('weekend: hidden one second before 06:00 EDT Monday',
    pg_temp.candidate_sql(6, 5), ARRAY['P0001']);
DO $$ BEGIN EXECUTE pg_temp.candidate_sql(7, 5);
    RAISE NOTICE 'ok - weekend filing visible at exactly 06:00 EDT Monday'; END $$;

DO $$
BEGIN
    IF (SELECT count(*) FROM retrieval_candidates
        WHERE org_id = '00000000-0000-0000-0000-000000001221') <> 6 THEN
        RAISE EXCEPTION 'not ok - expected exactly six admitted candidates';
    END IF;
    RAISE NOTICE 'ok - exactly the six visible candidates persisted';
END
$$;

RESET ROLE;


-- ---------------------------------------------------------------------------
-- 3. fel_public_read
-- ---------------------------------------------------------------------------

CREATE TEMP TABLE public_read_allowlist (relname text PRIMARY KEY);
INSERT INTO public_read_allowlist VALUES
    ('documents'), ('document_versions'), ('sections'), ('source_spans'),
    ('tables_meta'), ('financial_facts'), ('corpus_versions'),
    ('corpus_version_documents'), ('retrieval_index_versions'), ('retrieval_items');
GRANT SELECT ON public_read_allowlist TO fel_public_read;

DO $$
DECLARE
    r record;
    checked integer := 0;
BEGIN
    -- Role attributes: a plain NOLOGIN group role.
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'fel_public_read'
          AND NOT rolcanlogin AND NOT rolsuper
          AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolbypassrls
          AND NOT rolreplication
    ) THEN
        RAISE EXCEPTION 'not ok - fel_public_read is not a plain NOLOGIN role';
    END IF;
    RAISE NOTICE 'ok - fel_public_read is NOLOGIN, no superuser/createdb/createrole/bypassrls';

    -- No membership in any other role: no inherited tenant privilege.
    IF EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles mr ON mr.oid = m.member
               WHERE mr.rolname = 'fel_public_read') THEN
        RAISE EXCEPTION 'not ok - fel_public_read is a member of another role';
    END IF;
    RAISE NOTICE 'ok - fel_public_read is a member of no role';

    -- Every relation in public: exactly SELECT on the allowlist, nothing else.
    FOR r IN
        SELECT c.oid, c.relname, c.relkind,
               a.relname IS NOT NULL AS allowed
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN public_read_allowlist a ON a.relname = c.relname
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
    LOOP
        checked := checked + 1;
        IF has_table_privilege('fel_public_read', r.oid, 'SELECT') IS DISTINCT FROM r.allowed THEN
            RAISE EXCEPTION 'not ok - SELECT on % is %, expected %', r.relname,
                has_table_privilege('fel_public_read', r.oid, 'SELECT'), r.allowed;
        END IF;
        IF has_table_privilege('fel_public_read', r.oid,
                               'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') THEN
            RAISE EXCEPTION 'not ok - fel_public_read holds a write privilege on %', r.relname;
        END IF;
        IF NOT r.allowed AND has_any_column_privilege('fel_public_read', r.oid,
                                                      'SELECT, INSERT, UPDATE, REFERENCES') THEN
            RAISE EXCEPTION 'not ok - fel_public_read holds a column privilege on %', r.relname;
        END IF;
        IF r.allowed AND EXISTS (
            SELECT 1 FROM pg_attribute
            WHERE attrelid = r.oid AND attname = 'org_id' AND NOT attisdropped
        ) THEN
            RAISE EXCEPTION 'not ok - allowlisted table % carries org_id', r.relname;
        END IF;
    END LOOP;
    IF (SELECT count(*) FROM public_read_allowlist a
        WHERE has_table_privilege('fel_public_read', format('public.%I', a.relname), 'SELECT'))
       <> 10 THEN
        RAISE EXCEPTION 'not ok - an allowlisted table is not readable';
    END IF;
    RAISE NOTICE 'ok - fel_public_read: SELECT on exactly the 10 untenanted tables among % relations', checked;

    FOR r IN
        SELECT c.oid, c.relname FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'S'
    LOOP
        IF has_sequence_privilege('fel_public_read', r.oid, 'USAGE, SELECT, UPDATE') THEN
            RAISE EXCEPTION 'not ok - fel_public_read holds a privilege on sequence %', r.relname;
        END IF;
    END LOOP;
    RAISE NOTICE 'ok - fel_public_read holds no sequence privilege';

    IF has_schema_privilege('fel_public_read', 'public', 'CREATE') THEN
        RAISE EXCEPTION 'not ok - fel_public_read can create in schema public';
    END IF;
    RAISE NOTICE 'ok - fel_public_read cannot create in schema public';
END
$$;

-- Behavioral proof: every statement below runs as the role and must raise
-- 42501 (insufficient_privilege), not merely be absent from a catalog.
SET LOCAL ROLE fel_public_read;

DO $$
BEGIN
    IF (SELECT count(*) FROM documents
        WHERE entity_id = '00000000-0000-0000-0000-000000001200') <> 5
       OR (SELECT count(*) FROM retrieval_items
           WHERE index_version_id = '00000000-0000-0000-0000-000000001261') <> 5 THEN
        RAISE EXCEPTION 'not ok - fel_public_read cannot read the public corpus';
    END IF;
    RAISE NOTICE 'ok - fel_public_read reads documents and retrieval_items';
END
$$;

SELECT pg_temp.expect_rejection('fel_public_read SELECT ingestion_quarantine',
    'SELECT 1 FROM ingestion_quarantine LIMIT 0', ARRAY['42501']);
SELECT pg_temp.expect_rejection('fel_public_read SELECT ingestion_runs',
    'SELECT 1 FROM ingestion_runs LIMIT 0', ARRAY['42501']);
SELECT pg_temp.expect_rejection('fel_public_read SELECT retrieval_embeddings',
    'SELECT 1 FROM retrieval_embeddings LIMIT 0', ARRAY['42501']);
SELECT pg_temp.expect_rejection('fel_public_read SELECT schema_migrations',
    'SELECT 1 FROM schema_migrations LIMIT 0', ARRAY['42501']);

-- Every non-allowlisted table in public, including every tenant table.
DO $$
DECLARE
    r record;
    denied integer := 0;
BEGIN
    FOR r IN
        SELECT c.relname FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
          AND c.relname NOT IN (SELECT relname FROM public_read_allowlist)
        ORDER BY c.relname
    LOOP
        PERFORM pg_temp.expect_rejection(
            format('fel_public_read SELECT %s', r.relname),
            format('SELECT 1 FROM public.%I LIMIT 0', r.relname),
            ARRAY['42501']);
        denied := denied + 1;
    END LOOP;
    IF denied < 30 THEN
        RAISE EXCEPTION 'not ok - only % relations were denied; tenant tables missing?', denied;
    END IF;
    RAISE NOTICE 'ok - fel_public_read denied SELECT on all % other relations', denied;
END
$$;

-- Writes and DDL on the readable tables.
SELECT pg_temp.expect_rejection('fel_public_read INSERT documents', $sql$
    INSERT INTO documents (id, entity_id, accession, source_url, content_hash, storage_key, published_at)
    VALUES ('00000000-0000-0000-0000-0000000012f1', '00000000-0000-0000-0000-000000001200',
            'acc-12-write', 'https://example.test/12/w',
            'sha256:12f112f112f112f112f112f112f112f112f112f112f112f112f112f112f112f1', 'raw/w', now())
$sql$, ARRAY['42501']);
SELECT pg_temp.expect_rejection('fel_public_read UPDATE documents',
    $sql$UPDATE documents SET accepted_at = now(), timestamp_precision = 'second'
         WHERE id = '00000000-0000-0000-0000-000000001202'$sql$, ARRAY['42501']);
SELECT pg_temp.expect_rejection('fel_public_read DELETE source_spans',
    'DELETE FROM source_spans', ARRAY['42501']);
SELECT pg_temp.expect_rejection('fel_public_read TRUNCATE retrieval_items',
    'TRUNCATE retrieval_items', ARRAY['42501']);
SELECT pg_temp.expect_rejection('fel_public_read UPDATE retrieval_index_versions',
    $sql$UPDATE retrieval_index_versions SET diagnostics = '{}'::jsonb$sql$, ARRAY['42501']);
SELECT pg_temp.expect_rejection('fel_public_read row lock on documents',
    'SELECT 1 FROM documents FOR SHARE', ARRAY['42501']);
SELECT pg_temp.expect_rejection('fel_public_read CREATE TABLE',
    'CREATE TABLE public.fel_public_read_probe (id int)', ARRAY['42501']);

RESET ROLE;

ROLLBACK;
