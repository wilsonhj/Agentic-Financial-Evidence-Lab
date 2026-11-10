-- SEC acceptance time and the public read-only role (ADR-0034 decisions 2
-- and 4, issue #392, milestone tasks MCP-101 and MCP-102).
--
-- 1. documents.accepted_at / documents.timestamp_precision.
--    `published_at` is the EDGAR filing date at midnight UTC, so a cutoff
--    earlier on the same day admitted a filing accepted later that day
--    (design contract §4 P1). `accepted_at` stores the verified SEC
--    acceptance instant. `timestamp_precision` states what the row knows:
--    'date' (filing date only; accepted_at is NULL) or 'second' (a verified
--    acceptance instant). The CHECK makes the two columns agree in both
--    directions, so a row can never claim second precision without an
--    instant, nor carry an instant labeled as date-only. Existing rows take
--    the default 'date' with accepted_at NULL; #393 fills them.
--
-- 2. fel_guard_candidate (0003) compares the query cutoff against
--    COALESCE(accepted_at, published_at) AND still against published_at.
--    The second comparison is what keeps the guard never weaker than the
--    0003 rule: a filing accepted after 17:30 ET receives the NEXT business
--    day's filing date, so its accepted_at can precede its published_at
--    midnight. COALESCE alone would then admit it earlier than 0003 did.
--    Rejecting when either instant is after the cutoff removes the same-day
--    leak wherever the acceptance time is known and admits nothing the 0003
--    guard rejected. The rest of the function body is identical to 0003.
--
-- 3. fel_public_read: a NOLOGIN group role for the anonymous MCP surface
--    (ADR-0034 decision 2), created the way 0001/0008 create fel_app and
--    fel_worker. SELECT only, on the untenanted public-corpus tables (0002)
--    and the untenanted retrieval-index tables the keyword lanes read
--    (0003: retrieval_index_versions, retrieval_items). Deliberately NOT
--    granted: ingestion_quarantine and ingestion_runs (operational
--    internals), retrieval_embeddings (the dense lane is off on this
--    surface, decision 6), schema_migrations, and every tenant table. The
--    grant is guarded: the DO block below refuses to grant on any table that
--    has an org_id column, so a later tenancy change cannot silently widen
--    this role. Existing grants are unchanged.
--
-- Harness: tests/0012_acceptance_time_and_public_read.test.sql.

-- ---------------------------------------------------------------------------
-- 1. Acceptance time
-- ---------------------------------------------------------------------------

ALTER TABLE documents
    ADD COLUMN accepted_at timestamptz,
    ADD COLUMN timestamp_precision text NOT NULL DEFAULT 'date',
    ADD CONSTRAINT documents_timestamp_precision_check
        CHECK (timestamp_precision IN ('date', 'second')),
    ADD CONSTRAINT documents_accepted_at_precision_check
        CHECK ((accepted_at IS NOT NULL) = (timestamp_precision = 'second'));

COMMENT ON COLUMN documents.accepted_at IS
    'Verified SEC acceptance instant (acceptanceDateTime). NULL when unknown; '
    'then timestamp_precision is ''date'' and published_at is the only bound.';
COMMENT ON COLUMN documents.timestamp_precision IS
    '''second'' iff accepted_at is a verified acceptance instant; ''date'' '
    'when only the filing date (published_at) is known.';

-- Point-in-time listing on acceptance time:
-- WHERE entity_id = $1 AND accepted_at <= $2 (strict MCP visibility).
CREATE INDEX documents_entity_accepted_idx ON documents (entity_id, accepted_at);

-- ---------------------------------------------------------------------------
-- 2. Candidate cutoff guard
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fel_guard_candidate() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    run_index_id uuid;
    item_index_id uuid;
    effective_cutoff timestamptz;
    item_published_at timestamptz;
    item_accepted_at timestamptz;
BEGIN
    PERFORM fel_assert_run_open(NEW.run_id, NEW.org_id);
    SELECT q.index_version_id, q.effective_as_of
    INTO run_index_id, effective_cutoff
    FROM retrieval_runs r
    JOIN queries q ON q.id = r.query_id AND q.org_id = r.org_id
    WHERE r.id = NEW.run_id AND r.org_id = NEW.org_id;
    SELECT ri.index_version_id, d.published_at, d.accepted_at
    INTO item_index_id, item_published_at, item_accepted_at
    FROM retrieval_items ri
    JOIN documents d ON d.id = ri.document_id
    WHERE ri.id = NEW.retrieval_item_id;
    IF run_index_id IS DISTINCT FROM item_index_id THEN
        RAISE EXCEPTION 'candidate item index disagrees with its run query';
    END IF;
    IF COALESCE(item_accepted_at, item_published_at) > effective_cutoff
       OR item_published_at > effective_cutoff THEN
        RAISE EXCEPTION 'candidate evidence was published after the query cutoff';
    END IF;
    RETURN NEW;
END
$$;

-- ---------------------------------------------------------------------------
-- 3. Public read-only role
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'fel_public_read') THEN
        CREATE ROLE fel_public_read NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO fel_public_read;

DO $$
DECLARE
    public_tables CONSTANT text[] := ARRAY[
        -- 0002 public corpus
        'documents', 'document_versions', 'sections', 'source_spans',
        'tables_meta', 'financial_facts', 'corpus_versions',
        'corpus_version_documents',
        -- 0003 retrieval index read by the lexical, facts and tables lanes
        'retrieval_index_versions', 'retrieval_items'
    ];
    granted_table text;
BEGIN
    FOREACH granted_table IN ARRAY public_tables LOOP
        IF to_regclass(format('public.%I', granted_table)) IS NULL THEN
            RAISE EXCEPTION 'fel_public_read: table % does not exist', granted_table;
        END IF;
        IF EXISTS (
            SELECT 1 FROM pg_attribute
            WHERE attrelid = to_regclass(format('public.%I', granted_table))
              AND attname = 'org_id' AND NOT attisdropped
        ) THEN
            RAISE EXCEPTION 'fel_public_read: refusing SELECT on tenant table %', granted_table;
        END IF;
        EXECUTE format('GRANT SELECT ON public.%I TO fel_public_read', granted_table);
    END LOOP;
END
$$;

COMMENT ON ROLE fel_public_read IS
    'Anonymous MCP read surface (ADR-0034 decision 2): SELECT only on the '
    'untenanted public corpus and keyword retrieval index. No tenant table, '
    'no ingestion_quarantine, ingestion_runs or retrieval_embeddings, no write. '
    'Entered via SET ROLE on a dedicated pool that sets statement_timeout.';
