-- Harness for 0012_acceptance_time_and_public_read.sql (issue #392,
-- ADR-0034 decisions 2 and 4).
--
-- Three things are pinned here:
-- 1. documents.accepted_at / timestamp_precision: defaults, the CHECKs that
--    tie them together, and the (entity_id, accepted_at) index.
-- 2. fel_guard_candidate: a same-day filing accepted after the cutoff is
--    rejected; a NULL accepted_at falls back to published_at in both
--    directions; and an after-hours filing whose acceptance precedes its
--    filing-date midnight is still held to published_at (never weaker than
--    the 0003 rule). Candidates are inserted as fel_app, the role that
--    writes them in production.
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
    published_at, accepted_at, timestamp_precision
) VALUES
    -- Same-day: filing date 2024-03-06, accepted 15:00 ET (20:00Z).
    ('00000000-0000-0000-0000-000000001201', '00000000-0000-0000-0000-000000001200',
     'acc-12-same-day', 'https://example.test/12/1',
     'sha256:1201120112011201120112011201120112011201120112011201120112011201', 'raw/1201',
     '2024-03-06T00:00:00Z', '2024-03-06T20:00:00Z', 'second'),
    -- After hours: accepted 17:45 ET on 03-06 (22:45Z), filing date 03-07.
    ('00000000-0000-0000-0000-000000001203', '00000000-0000-0000-0000-000000001200',
     'acc-12-after-hours', 'https://example.test/12/3',
     'sha256:1203120312031203120312031203120312031203120312031203120312031203', 'raw/1203',
     '2024-03-07T00:00:00Z', '2024-03-06T22:45:00Z', 'second');
-- Date-only: no acceptance time; the defaults must apply.
INSERT INTO documents (
    id, entity_id, accession, source_url, content_hash, storage_key, published_at
) VALUES
    ('00000000-0000-0000-0000-000000001202', '00000000-0000-0000-0000-000000001200',
     'acc-12-date-only', 'https://example.test/12/2',
     'sha256:1202120212021202120212021202120212021202120212021202120212021202', 'raw/1202',
     '2024-03-06T00:00:00Z');

DO $$
BEGIN
    IF (SELECT ROW(accepted_at, timestamp_precision) FROM documents
        WHERE id = '00000000-0000-0000-0000-000000001202')
       IS DISTINCT FROM ROW(NULL::timestamptz, 'date'::text) THEN
        RAISE EXCEPTION 'not ok - legacy insert did not default to (NULL, date)';
    END IF;
    RAISE NOTICE 'ok - legacy insert defaults to accepted_at NULL, precision date';

    IF NOT EXISTS (
        SELECT 1
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        WHERE c.relname = 'documents_entity_accepted_idx'
          AND i.indrelid = 'documents'::regclass
          AND (SELECT array_agg(a.attname::text ORDER BY k.ord)
               FROM unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord)
               JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum)
              = ARRAY['entity_id', 'accepted_at']
    ) THEN
        RAISE EXCEPTION 'not ok - (entity_id, accepted_at) index missing';
    END IF;
    RAISE NOTICE 'ok - documents_entity_accepted_idx covers (entity_id, accepted_at)';
END
$$;

SELECT pg_temp.expect_rejection('second precision without accepted_at', $sql$
    INSERT INTO documents (id, entity_id, accession, source_url, content_hash, storage_key,
                           published_at, timestamp_precision)
    VALUES ('00000000-0000-0000-0000-000000001211', '00000000-0000-0000-0000-000000001200',
            'acc-12-bad-1', 'https://example.test/12/b1',
            'sha256:1211121112111211121112111211121112111211121112111211121112111211', 'raw/b1',
            '2024-03-06T00:00:00Z', 'second')
$sql$, ARRAY['23514']);
SELECT pg_temp.expect_rejection('accepted_at labeled date precision', $sql$
    INSERT INTO documents (id, entity_id, accession, source_url, content_hash, storage_key,
                           published_at, accepted_at)
    VALUES ('00000000-0000-0000-0000-000000001212', '00000000-0000-0000-0000-000000001200',
            'acc-12-bad-2', 'https://example.test/12/b2',
            'sha256:1212121212121212121212121212121212121212121212121212121212121212', 'raw/b2',
            '2024-03-06T00:00:00Z', '2024-03-06T20:00:00Z')
$sql$, ARRAY['23514']);
SELECT pg_temp.expect_rejection('unknown timestamp precision', $sql$
    INSERT INTO documents (id, entity_id, accession, source_url, content_hash, storage_key,
                           published_at, accepted_at, timestamp_precision)
    VALUES ('00000000-0000-0000-0000-000000001213', '00000000-0000-0000-0000-000000001200',
            'acc-12-bad-3', 'https://example.test/12/b3',
            'sha256:1213121312131213121312131213121312131213121312131213121312131213', 'raw/b3',
            '2024-03-06T00:00:00Z', '2024-03-06T20:00:00Z', 'approximate')
$sql$, ARRAY['23514']);
SELECT pg_temp.expect_rejection('null timestamp precision', $sql$
    INSERT INTO documents (id, entity_id, accession, source_url, content_hash, storage_key,
                           published_at, timestamp_precision)
    VALUES ('00000000-0000-0000-0000-000000001214', '00000000-0000-0000-0000-000000001200',
            'acc-12-bad-4', 'https://example.test/12/b4',
            'sha256:1214121412141214121412141214121412141214121412141214121412141214', 'raw/b4',
            '2024-03-06T00:00:00Z', NULL)
$sql$, ARRAY['23502']);

-- ---------------------------------------------------------------------------
-- 2. fel_guard_candidate on acceptance time
-- ---------------------------------------------------------------------------

INSERT INTO organizations (id, name)
VALUES ('00000000-0000-0000-0000-000000001221', 'Acceptance Org');
INSERT INTO memberships (org_id, user_id, role)
VALUES ('00000000-0000-0000-0000-000000001221', '00000000-0000-0000-0000-000000001222', 'owner');
INSERT INTO workspaces (id, org_id, name, entity_id, base_currency, fiscal_calendar, as_of)
VALUES ('00000000-0000-0000-0000-000000001223', '00000000-0000-0000-0000-000000001221',
        'Acceptance WS', '00000000-0000-0000-0000-000000001200', 'USD', 'calendar',
        '2030-01-01T00:00:00Z');

INSERT INTO document_versions (id, document_id, parser_version, normalizer_version,
                               canonical_text_key)
VALUES
    ('00000000-0000-0000-0000-000000001231', '00000000-0000-0000-0000-000000001201', 'p1', 'n1', 'text/1231'),
    ('00000000-0000-0000-0000-000000001232', '00000000-0000-0000-0000-000000001202', 'p1', 'n1', 'text/1232'),
    ('00000000-0000-0000-0000-000000001233', '00000000-0000-0000-0000-000000001203', 'p1', 'n1', 'text/1233');
INSERT INTO sections (id, document_version_id, heading, heading_path, ord, start_char, end_char)
VALUES
    ('00000000-0000-0000-0000-000000001241', '00000000-0000-0000-0000-000000001231', 'S', ARRAY['S'], 0, 0, 10),
    ('00000000-0000-0000-0000-000000001242', '00000000-0000-0000-0000-000000001232', 'S', ARRAY['S'], 0, 0, 10),
    ('00000000-0000-0000-0000-000000001243', '00000000-0000-0000-0000-000000001233', 'S', ARRAY['S'], 0, 0, 10);
INSERT INTO source_spans (id, document_version_id, section_id, start_char, end_char, text_hash)
VALUES
    ('00000000-0000-0000-0000-000000001251', '00000000-0000-0000-0000-000000001231', '00000000-0000-0000-0000-000000001241', 0, 10,
     'sha256:1251125112511251125112511251125112511251125112511251125112511251'),
    ('00000000-0000-0000-0000-000000001252', '00000000-0000-0000-0000-000000001232', '00000000-0000-0000-0000-000000001242', 0, 10,
     'sha256:1252125212521252125212521252125212521252125212521252125212521252'),
    ('00000000-0000-0000-0000-000000001253', '00000000-0000-0000-0000-000000001233', '00000000-0000-0000-0000-000000001243', 0, 10,
     'sha256:1253125312531253125312531253125312531253125312531253125312531253');
INSERT INTO corpus_versions (id, label, status, is_active, published_at)
VALUES ('00000000-0000-0000-0000-000000001260', 'Acceptance corpus', 'superseded', false, now());
INSERT INTO corpus_version_documents (corpus_version_id, document_version_id)
VALUES
    ('00000000-0000-0000-0000-000000001260', '00000000-0000-0000-0000-000000001231'),
    ('00000000-0000-0000-0000-000000001260', '00000000-0000-0000-0000-000000001232'),
    ('00000000-0000-0000-0000-000000001260', '00000000-0000-0000-0000-000000001233');
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
VALUES
    ('00000000-0000-0000-0000-000000001271', '00000000-0000-0000-0000-000000001261', 'passage',
     '00000000-0000-0000-0000-000000001200', '00000000-0000-0000-0000-000000001201',
     '00000000-0000-0000-0000-000000001231', '00000000-0000-0000-0000-000000001241',
     '00000000-0000-0000-0000-000000001251', 'same day',
     'sha256:1271127112711271127112711271127112711271127112711271127112711271', 0, 10, 2),
    ('00000000-0000-0000-0000-000000001272', '00000000-0000-0000-0000-000000001261', 'passage',
     '00000000-0000-0000-0000-000000001200', '00000000-0000-0000-0000-000000001202',
     '00000000-0000-0000-0000-000000001232', '00000000-0000-0000-0000-000000001242',
     '00000000-0000-0000-0000-000000001252', 'date only',
     'sha256:1272127212721272127212721272127212721272127212721272127212721272', 0, 10, 2),
    ('00000000-0000-0000-0000-000000001273', '00000000-0000-0000-0000-000000001261', 'passage',
     '00000000-0000-0000-0000-000000001200', '00000000-0000-0000-0000-000000001203',
     '00000000-0000-0000-0000-000000001233', '00000000-0000-0000-0000-000000001243',
     '00000000-0000-0000-0000-000000001253', 'after hours',
     'sha256:1273127312731273127312731273127312731273127312731273127312731273', 0, 10, 2);
UPDATE retrieval_index_versions SET status = 'ready', published_at = now()
    WHERE id = '00000000-0000-0000-0000-000000001261';

-- One query per cutoff. q1: 09:00 ET on 03-06. q2: 18:00 ET on 03-06.
-- q3: before the filing date. q4: just after the 03-07 filing-date midnight.
INSERT INTO queries (id, org_id, workspace_id, created_by, question, effective_as_of,
                     corpus_version_id, index_version_id, plan, planner_version)
VALUES
    ('00000000-0000-0000-0000-000000001281', '00000000-0000-0000-0000-000000001221',
     '00000000-0000-0000-0000-000000001223', '00000000-0000-0000-0000-000000001222',
     'morning', '2024-03-06T14:00:00Z', '00000000-0000-0000-0000-000000001260',
     '00000000-0000-0000-0000-000000001261', '{}'::jsonb, 'planner-v1'),
    ('00000000-0000-0000-0000-000000001282', '00000000-0000-0000-0000-000000001221',
     '00000000-0000-0000-0000-000000001223', '00000000-0000-0000-0000-000000001222',
     'evening', '2024-03-06T23:00:00Z', '00000000-0000-0000-0000-000000001260',
     '00000000-0000-0000-0000-000000001261', '{}'::jsonb, 'planner-v1'),
    ('00000000-0000-0000-0000-000000001283', '00000000-0000-0000-0000-000000001221',
     '00000000-0000-0000-0000-000000001223', '00000000-0000-0000-0000-000000001222',
     'day before', '2024-03-05T12:00:00Z', '00000000-0000-0000-0000-000000001260',
     '00000000-0000-0000-0000-000000001261', '{}'::jsonb, 'planner-v1'),
    ('00000000-0000-0000-0000-000000001284', '00000000-0000-0000-0000-000000001221',
     '00000000-0000-0000-0000-000000001223', '00000000-0000-0000-0000-000000001222',
     'next day', '2024-03-07T01:00:00Z', '00000000-0000-0000-0000-000000001260',
     '00000000-0000-0000-0000-000000001261', '{}'::jsonb, 'planner-v1');
INSERT INTO retrieval_runs (id, org_id, query_id, mode, config_hash, embedding_provider,
                            embedding_model, planner_version)
SELECT ('00000000-0000-0000-0000-00000000129' || n)::uuid,
       '00000000-0000-0000-0000-000000001221',
       ('00000000-0000-0000-0000-00000000128' || n)::uuid,
       'execute',
       'sha256:1290129012901290129012901290129012901290129012901290129012901290',
       'none', 'none', 'planner-v1'
FROM generate_series(1, 4) AS n;
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


-- q1, 09:00 ET: the same-day filing accepted at 15:00 ET is hidden. Under
-- the 0003 rule (published_at midnight <= cutoff) it was admitted: the P1 leak.
SELECT pg_temp.expect_rejection('same-day filing accepted after the cutoff',
    pg_temp.candidate_sql(1, 1), ARRAY['P0001']);
-- q1: NULL accepted_at falls back to published_at, which is before the cutoff.
DO $$ BEGIN EXECUTE pg_temp.candidate_sql(1, 2);
    RAISE NOTICE 'ok - NULL accepted_at falls back to published_at (admitted)'; END $$;
-- q1: after-hours filing is hidden on both counts.
SELECT pg_temp.expect_rejection('after-hours filing before acceptance',
    pg_temp.candidate_sql(1, 3), ARRAY['P0001']);

-- q2, 18:00 ET: the same-day filing is now accepted and visible.
DO $$ BEGIN EXECUTE pg_temp.candidate_sql(2, 1);
    RAISE NOTICE 'ok - same-day filing accepted before the cutoff is admitted'; END $$;
-- q2: accepted 17:45 ET <= cutoff, but its filing-date midnight (03-07) is
-- after the cutoff. The 0003 guard rejected it, so 0012 must too.
SELECT pg_temp.expect_rejection('after-hours filing held to its filing date (never weaker)',
    pg_temp.candidate_sql(2, 3), ARRAY['P0001']);

-- q3: NULL accepted_at falls back to published_at, which is after the cutoff.
SELECT pg_temp.expect_rejection('NULL accepted_at falls back to published_at (rejected)',
    pg_temp.candidate_sql(3, 2), ARRAY['P0001']);

-- q4: past both instants, the after-hours filing is admitted.
DO $$ BEGIN EXECUTE pg_temp.candidate_sql(4, 3);
    RAISE NOTICE 'ok - after-hours filing admitted once both instants pass'; END $$;

DO $$
BEGIN
    IF (SELECT count(*) FROM retrieval_candidates
        WHERE org_id = '00000000-0000-0000-0000-000000001221') <> 3 THEN
        RAISE EXCEPTION 'not ok - expected exactly three admitted candidates';
    END IF;
    RAISE NOTICE 'ok - exactly the three visible candidates persisted';
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
        WHERE entity_id = '00000000-0000-0000-0000-000000001200') <> 3
       OR (SELECT count(*) FROM retrieval_items
           WHERE index_version_id = '00000000-0000-0000-0000-000000001261') <> 3 THEN
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
