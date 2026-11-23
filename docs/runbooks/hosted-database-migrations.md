# Hosted database migrations

How to apply `db/migrations` to the hosted Neon database that ADR-0035 puts
behind the Vercel project. Every path below uses the ledger applier,
[`scripts/db/migrate.py`](../../scripts/db/migrate.py) (ADR-0014), and runs
[`scripts/db/check_server.py`](../../scripts/db/check_server.py) first.

## Before the first run

The database was created through the Vercel Marketplace as `fel-db` (Neon free
plan, region `iad1`). Vercel injects `DATABASE_URL`, `DATABASE_URL_UNPOOLED`
and the `PG*` / `POSTGRES_*` variables into `financial-evidence-lab-web` for
production and preview.

Migrations need the **owner role's direct (unpooled) connection string**:
`DATABASE_URL_UNPOOLED`, or "Direct connection" in the Neon console. The
pooled URL goes through PgBouncer in transaction mode, which drops the session
advisory lock `migrate.py` holds while it applies.

`check_server.py` refuses the database unless it is PostgreSQL 18 or later and
offers pgvector 0.8.2 or later. On an older server, `0001` and `0002` would
apply before `0003` failed, leaving a half-migrated database.

## GitHub Actions (the normal path)

Workflow: [`.github/workflows/db-migrate.yml`](../../.github/workflows/db-migrate.yml),
"DB — migrate the hosted database".

One-time setup, by the repository owner:

1. Settings → Environments → New environment, named `hosted-database`.
2. Add yourself under **Required reviewers**, so every run waits for approval.
3. Under **Deployment branches and tags**, allow `main` only.
4. Add the environment secret `NEON_DATABASE_URL` with the direct owner URL.

Each run:

1. Actions → "DB — migrate the hosted database" → Run workflow, on `main`.
2. Pick a mode:
   - `check` reports whether anything is pending or drifted (exit 2 or 3).
   - `dry-run` prints the plan without applying anything.
   - `apply` applies every pending migration, each in its own transaction with
     its ledger row, then re-runs `--check`.
3. Approve the run when GitHub asks.

`apply` refuses to run from any branch but `main`, so only reviewed
migrations reach the hosted database. Runs never overlap: the workflow uses a
concurrency group, and `migrate.py` also takes an advisory lock.

## From a workstation

For the first migration or a recovery, from a checkout of `main` on a machine
that can reach Neon on port 5432:

```sh
pip install --require-hashes -r requirements.lock
# Use the variable, not --database-url, to keep the URL out of the process list.
export FEL_DATABASE_URL='<direct owner URL>'
python scripts/db/check_server.py
python scripts/db/migrate.py --dry-run
python scripts/db/migrate.py
python scripts/db/migrate.py --check
unset FEL_DATABASE_URL
```

`check_server.py` prints the server version, the pgvector version on offer and
the connected role. Stop if it exits 6.

## Exit codes

| Code | Meaning | What to do |
|---|---|---|
| 0 | Applied, up to date, or the check passed | Nothing |
| 2 | `--check`: migrations are pending | Run `apply` |
| 3 | A migration already applied has changed on disk | Do not edit applied migrations; add a new one |
| 4 | A migration failed; its transaction was rolled back | Read the error and fix it in a new PR |
| 5 | Could not connect | Check the URL, and that it is the direct one |
| 6 | Server or pgvector too old (`check_server.py`) | Use a PostgreSQL 18 database |

## Not covered yet

- The app still connects as the owner role (#423). A least-privilege runtime
  role, with the owner URL kept only in this environment, is the follow-up.
- Preview deployments share the production database until Neon
  branch-per-preview is set up.
