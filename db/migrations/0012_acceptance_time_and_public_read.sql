-- SEC acceptance and publication time, and the public read-only role
-- (ADR-0034 decisions 2 and 4 with Amendment 1, issue #392, milestone tasks
-- MCP-101 and MCP-102).
--
-- 1. documents.accepted_at / public_at / public_at_basis / timestamp_precision.
--    `published_at` is the EDGAR filing date at midnight UTC, so a cutoff
--    earlier on the same day admitted a filing made public later that day
--    (design contract §4 P1). Acceptance is not publication: most
--    submissions begun after 17:30 ET get the next business day's filing date
--    and are not disseminated until that day (ADR-0034 Amendment 1). So the
--    row stores both instants:
--    * accepted_at: the verified SEC acceptance instant (acceptanceDateTime).
--    * public_at: the instant the filing became public, the visibility
--      instant. This migration does NOT compute it. One ingestion function
--      owned by #393 derives it (rule in the column comments).
--    * public_at_basis: how public_at was derived ('acceptance' or
--      'next_session_open').
--    * timestamp_precision: 'second' when the three are known, else 'date'
--      (only the filing date in published_at is known).
--    The CHECKs make the three columns all-or-nothing, tie precision to them
--    in both directions, forbid publication before acceptance, and tie the
--    basis to whether public_at equals accepted_at. Existing rows take the
--    default 'date' with all three NULL; #393 fills them.
--
-- 2. fel_guard_candidate (0003) rejects a candidate when
--    GREATEST(COALESCE(public_at, published_at), published_at) is after the
--    query cutoff. That is the expression the retrieval lanes use (#394). It
--    is never weaker than the 0003 rule (published_at > cutoff) by
--    construction, and it removes the same-day leak wherever public_at is
--    known. The rest of the function body is identical to 0003.
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
-- 1. Acceptance and publication time
-- ---------------------------------------------------------------------------

ALTER TABLE documents
    ADD COLUMN accepted_at timestamptz,
    ADD COLUMN public_at timestamptz,
    ADD COLUMN public_at_basis text,
    ADD COLUMN timestamp_precision text NOT NULL DEFAULT 'date',
    ADD CONSTRAINT documents_timestamp_precision_check
        CHECK (timestamp_precision IN ('date', 'second')),
    ADD CONSTRAINT documents_public_at_basis_check
        CHECK (public_at_basis IN ('acceptance', 'next_session_open')),
    -- accepted_at, public_at and public_at_basis are all set or all NULL.
    ADD CONSTRAINT documents_publication_all_or_none_check
        CHECK ((accepted_at IS NULL) = (public_at IS NULL)
               AND (public_at IS NULL) = (public_at_basis IS NULL)),
    -- 'second' iff the instants are known (and so, by the CHECK above, all three).
    ADD CONSTRAINT documents_accepted_at_precision_check
        CHECK ((accepted_at IS NOT NULL) = (timestamp_precision = 'second')),
    ADD CONSTRAINT documents_public_after_acceptance_check
        CHECK (public_at >= accepted_at),
    ADD CONSTRAINT documents_public_at_basis_consistency_check
        CHECK ((public_at_basis = 'acceptance') = (public_at = accepted_at));

COMMENT ON COLUMN documents.accepted_at IS
    'Verified SEC acceptance instant (acceptanceDateTime). NULL when unknown; '
    'then public_at and public_at_basis are NULL, timestamp_precision is '
    '''date'' and published_at is the only bound.';
COMMENT ON COLUMN documents.public_at IS
    'Instant the filing became public; the visibility instant (ADR-0034 '
    'decision 4, Amendment 1). Derived by one ingestion function (#393), not '
    'by SQL: if the filing date is later than the America/New_York calendar '
    'date of accepted_at, 06:00 America/New_York on the filing date '
    '(basis next_session_open); otherwise accepted_at (basis acceptance). '
    'next_session_open is the earliest the filing could have been public; '
    'acceptance treats intraday dissemination delay as zero.';
COMMENT ON COLUMN documents.public_at_basis IS
    'acceptance: public_at = accepted_at. next_session_open: public_at is '
    '06:00 America/New_York on the filing date, when EDGAR opens.';
COMMENT ON COLUMN documents.timestamp_precision IS
    '''second'' iff accepted_at/public_at are verified instants; ''date'' '
    'when only the filing date (published_at) is known.';

-- Point-in-time listing on publication time:
-- WHERE entity_id = $1 AND public_at <= $2 (strict MCP visibility).
CREATE INDEX documents_entity_public_idx ON documents (entity_id, public_at);

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
    item_visible_at timestamptz;
BEGIN
    PERFORM fel_assert_run_open(NEW.run_id, NEW.org_id);
    SELECT q.index_version_id, q.effective_as_of
    INTO run_index_id, effective_cutoff
    FROM retrieval_runs r
    JOIN queries q ON q.id = r.query_id AND q.org_id = r.org_id
    WHERE r.id = NEW.run_id AND r.org_id = NEW.org_id;
    SELECT ri.index_version_id,
           GREATEST(COALESCE(d.public_at, d.published_at), d.published_at)
    INTO item_index_id, item_visible_at
    FROM retrieval_items ri
    JOIN documents d ON d.id = ri.document_id
    WHERE ri.id = NEW.retrieval_item_id;
    IF run_index_id IS DISTINCT FROM item_index_id THEN
        RAISE EXCEPTION 'candidate item index disagrees with its run query';
    END IF;
    IF item_visible_at > effective_cutoff THEN
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
