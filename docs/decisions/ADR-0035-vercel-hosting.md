# ADR-0035: Host the web app and API on Vercel, with Neon Postgres 18

Status: Proposed
Date: 2026-11-15
Supersedes in part: [ADR-0002](ADR-0002-mvp-stack.md), "Runtime and operations",
the line "Railway hosts the web, API, and worker processes from one monorepo".
Everything else in ADR-0002 stands.
Related: #428 (hosted build never run), #429 (no delivery pipeline), #427
(local-directory storage), #424 and #425 (work moved onto the job queue).

## Context

ADR-0002 chose Railway for the web app, API and worker. Nothing was ever
deployed there: the Railway builder is documented as unverifiable from CI
(`infra/railway/README.md`), no database or storage was provisioned (#61,
#108), and the 2026-11-14 production review lists the unexercised build as a
deploy blocker (#428).

The owner wants to run on free plans. They hold a Vercel Hobby account, AWS
credits that expire, OpenRouter credits, and a Claude Max plan that includes
monthly Claude API credit. The research behind this ADR (Railway, Vercel, AWS
and Neon plan terms, read 2026-11-15) found:

- Railway's free plan is USD 1 of usage a month with 0.5 GB per service, so
  three always-on services cost money.
- AWS's free plan ends six months after the account opens, after which the
  account is suspended unless it is upgraded.
- Vercel Hobby now runs multi-service projects (a Next.js frontend and a
  backend in one project), a container runtime, and queues, all in beta on
  every plan. Functions and containers there get 300 s per request and 2 GB of
  memory.
- Neon's free plan ships pgvector 0.8.6 on Postgres 18 and 0.8.0 on Postgres
  14 to 17. Migration `0003` refuses anything below 0.8.2, the release that
  fixes CVE-2026-3172.

## Decision

1. **Vercel is the host of record** for the web app and the API, deployed as
   one project with two services defined in the root `vercel.json`:
   - `web`: the Next.js app in `apps/web`.
   - `api`: the FastAPI app, built by the Vercel container runtime from
     `infra/docker/api.Dockerfile`. The image installs through the existing
     hash-locked `scripts/runtime/install.sh`, keeps Python 3.11, and runs as
     an unprivileged user on `PORT` 8080.
2. **The API is private.** Only `/health` is on the public route table. The web
   service reaches the API through a service binding.
3. **The container runtime, not the Python runtime, builds the API.** The
   Python runtime installs dependencies from one manifest in the service root
   and supports Python 3.12 and later only. The API needs five first-party
   wheels from across the monorepo and the repo pins 3.11.
4. **The database is Neon Postgres 18**, added through the Vercel Marketplace.
   CI moves from `pgvector/pgvector:0.8.5-pg17` to `0.8.6-pg18` so tests run on
   the hosted major version.
5. **Railway configuration stays until the first hosted deployment with a
   database passes**, then `infra/railway/` is deleted and #362 (Railway
   extraction worker) is closed or rewritten.

## Trial evidence (2026-11-15)

- The image builds (339 MB) from the hash-locked install. `/health` returns
  200 as uid 10001, and business routes fail closed with 503
  `AUTH_UNAVAILABLE` in the default public mode.
- A preview on the Vercel project `fel-demo`, with the framework preset set to
  Services, built both services in about 100 seconds. `/health` returned the
  API's payload from the container, and the runtime logs show uvicorn on port
  8080. `/v1/...` paths returned the web app's 404 page, so the API was not
  publicly reachable.
- Locally, all 13 migrations, the backup-and-restore smoke test and all 10
  migration harnesses pass on Postgres 18 with pgvector 0.8.6, and on
  Postgres 17. The Python suite passes on Python 3.12 with Postgres 18.
- Postgres 18 reports `ON DELETE RESTRICT` violations as SQLSTATE 23001
  (`restrict_violation`) where 17 used 23503. The `0009` harness now accepts
  either code. Inserts with a missing parent still raise 23503 on both, which
  is the only case the API handles.

## Consequences

- The Vercel project must use the Services framework preset and the repository
  root as its root directory. With the Next.js preset, Vercel ignores the
  `services` block and builds only the web app. Until the owner switches the
  project of record, `main` keeps building the web app as today.
- `PORT=8080` must be set on the project, because the image cannot bind port 80
  as a non-root user.
- Hobby is for personal, non-commercial use. Exceeding a quota pauses the
  feature, in most cases for 30 days. Paying users mean moving to Pro.
- Each API request is limited to 300 s. Long work must leave the request path:
  retrieval and index builds move onto the job queue (#424, #425), drained by
  queue-triggered functions. Extraction's 600 s budget has to be split by
  stage.
- API and worker can no longer share a disk. Storage moves to Vercel Blob
  behind one `StorageProvider` (#427).
- The container runtime, multi-service projects and queues are beta features.

## Not yet verified

- That the Vercel Marketplace lets the owner pick Postgres 18 when creating the
  Neon database, and that migrations apply there with the owner's rights.
- The URL scheme the service binding injects. The web app requires an HTTPS
  `FEL_API_BASE_URL` outside local development, so the trial binds the API URL
  to `FEL_API_SERVICE_URL` until the scheme is known.
- Cold-start time of the API container after it scales down.

## Alternatives considered

- **Railway.** Rejected for cost and because its build path was never proven.
- **AWS.** Rejected as the main host because the free plan expires. The
  credits are better spent on short jobs such as the #61 load test.
- **Vercel's Python runtime for the API.** Rejected for the reasons in
  decision 3.
