# External Claude agent handoff: FEL Helm lab

Read the [reproduction guide](../../docs/research/2026-11-15-kubernetes-helm-lab.md)
and [GitOps guide](GITOPS.md). This is an optional local lab under issue #435,
branch `agent/435-helm-lab`, draft PR #436. Baseline application commit is
`5a7b833c385131fa83388a93d6c3363211209832`; resolve the current PR head before
resuming. Read `AGENTS.md`, its prerequisite documents and current GitHub
issue/PR state. Keep the original working tree's changes intact.

The owner requested a repeatable Helm deployment/test workflow for Apple
Silicon Macs with 16, 24 and 32 GB memory. Reproduce the local lab first using
`bootstrap-tools.sh` and `lab.sh`. The scripts neither provision production nor
activate live providers. Docker Desktop must already be installed and running.

## Execution order

1. Use a clean checkout of the reviewed commit. Record architecture, source SHA,
   Docker memory, tool versions and image IDs. Build natively for ARM64.
2. Run `lab.sh doctor`, `build`, `create`, `deploy`, `test`, `status` and `open`.
   Use explicit `FEL_LAB_STATE` and `FEL_LAB_CLUSTER` values for this run.
   Run `python3 -m unittest discover -s infra/kubernetes/tests -v` for the
   credential and committed-build-context checks. Build only from the exported
   committed tree; the chart generates its disposable DB password at runtime.
3. Inspect the fixture UI through the loopback port forward. Verify the deployed
   Service smoke and separate real cross-stack acceptance Job both succeed.
   Save timestamped logs and workload/events output before another run.
4. Review any failure at its first broken boundary. A healthy Pod is insufficient.
   Keep the existing acceptance assertions and fail-closed deployment modes.
5. Only after baseline success, follow `GITOPS.md` to publish a versioned chart
   with immutable image references and promote a single local environment.
   Report registry publication and controller installation separately from
   offline manifest validation. Use credential names/references, never values
   in prompts, commits or reports.
6. Run local cleanup with `lab.sh delete` when the test cluster is no longer
   needed. Do not delete unrelated containers, clusters or volumes.

## Scope and review boundaries

- Approved file ownership is recorded in issue #435 and `workstreams.yaml`.
  Root/shared configuration and existing application guards are outside this
  implementation except the explicit additive workstream registration.
- Draft #431 owns `infra/docker/**`, root `.dockerignore`, CI and its hosting
  ADR. Coordinate before reusing or editing those files.
- The fixture Deployment and acceptance Job are distinct. Do not describe the
  former as a working public database-backed application.
- The existing acceptance harness invokes the real worker with scoped mock
  output. Do not replace it with an idle generic worker and infer success from
  its health endpoint.
- Do not modify `specs/**`, check task boxes, bypass public auth, permit remote
  synthetic targets, add owner-key fallback or claim real SEC/model acceptance.
- Argo CD/Kargo examples are local delivery configuration. Their installation
  does not replace the production hosting decision or release requirements.

## Required report

Report commit SHA, image digests, cluster/tool versions and allocated resources;
each command's exit status; the two test Job outcomes; observed UI route;
which browser/API/DB/worker boundaries ran; artifact paths; unrun steps;
cleanup state; and next action. Update the draft PR with reproducible evidence.
Different-vendor review by this external Claude agent can review this
OpenAI-authored change, subject to the repository's actual review rules.
