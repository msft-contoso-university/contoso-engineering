# Candidate software runtime integration

Story: [engineering #8](https://github.com/msft-contoso-university/contoso-engineering/issues/8).

This external harness starts the four actual pinned applications through ASP.NET
Core TestServer and migrates three independent disposable SQL Server databases.
Web requests use real MVC forms and antiforgery; service-to-service requests use
the production HTTP clients, reference lookup and bearer authorization policies.
Records are seeded through public service APIs, not shared database writes.

The test assembly alone supplies a synthetic signing authority, Web authentication
and credential adapters. It does not change application authentication code.
Application bearer validation still checks signature, issuer, audience, scopes
and roles. A controlled transport fault exercises visible dependency failure.
This is not proof of live OAuth federation, TLS sockets, Azure networking,
Application Insights ingestion or SRE. The fixed SQL password is for the isolated
ephemeral CI container only; it is not a deployment credential.

## Running

Materialize `contracts/runtime-candidates.json` commits in sibling
`services/contoso-{web,students,academics,enrollments}` directories. All pins are
unapproved candidates, not release inputs. Set `CONTOSO_RUNTIME_SOURCES` to that
absolute services directory and `CONTOSO_RUNTIME_SQL_CONNECTION` to the disposable
`127.0.0.1,1433` or `localhost,1433` SQL instance. Missing SQL fails; it never
falls back to SQLite or skips cases.

```powershell
python tools\runtime_checks.py sources --directory $env:CONTOSO_RUNTIME_SOURCES
dotnet restore tests\RuntimeIntegration\RuntimeIntegration.csproj --locked-mode
dotnet build tests\RuntimeIntegration\RuntimeIntegration.csproj -c Release --no-restore
dotnet test tests\RuntimeIntegration\RuntimeIntegration.csproj -c Release --no-build --no-restore --logger trx --results-directory artifacts\runtime
python tools\runtime_checks.py results --directory artifacts\runtime
```

For another checkout layout pass `-p:CandidateSourcesRoot=<absolute-directory>`
consistently to restore/build/test. Tests delete only their GUID-named
`AdlcRuntime_*` databases on the explicitly allowed loopback server. Cleanup
failure is a test failure, not silently ignored.

The GitHub workflow uploads complete TRX plus exact source pins and harness SHA.
All seven required named journeys/refusals must pass; missing/skipped/failed
reports cannot satisfy the aggregate. Existing frozen consumer checks are
unchanged. This remains a candidate gate until independently reviewed and wired
into trusted producer/release policy; a green standalone run is not promotion.

## Service pull requests

Story: [engineering #13](https://github.com/msft-contoso-university/contoso-engineering/issues/13).
The separate `runtime-service-pr.yml` reusable workflow runs this same harness
against the calling service's exact PR head, not the frozen candidate manifest.
Its required inputs are `service` (`web`, `students`, `academics` or
`enrollments`) and `candidate-sha` (`github.event.pull_request.head.sha`).
Only `pull_request` callers in the matching allowlisted service repository are
accepted. Merge SHAs, floating refs, other repositories and dispatch/target
events fail. It does not declare or inherit any secrets.

Before any service restore/build/test, the planner reads each of the other
three repositories' `refs/heads/main`, validates a full commit object, and
records the four-SHA snapshot. This is one recorded set of independently
resolved main commits, not an atomic transaction across repositories.
Subsequent checkouts use only those full SHAs; the source verifier rejects a
missing, linked, dirty or mismatched checkout. Nothing falls back to frozen
pins, a moving branch, mock service applications, SQLite or skipped tests.
Here "approved source" means the allowlisted service PR head or peer main
snapshot; it is not production/release approval.

The workflow fixes the Engineering harness/policy to a separate immutable
`HARNESS_COMMIT`. This is intentionally not `github.sha` or
`github.workflow_sha`, which describe the **caller**, not the reusable workflow.
Both Engineering checkout steps use this same control commit. Harness upgrades
require a reviewed commit followed by a reviewed workflow pin update.

Callers must pin the reusable workflow itself to a **reviewed full Engineering
commit** containing it, grant only `contents: read`, and omit `secrets` (never
`secrets: inherit`). For example, replace the marker below with that reviewed
40-character commit; it is deliberately not a runnable floating reference:

```yaml
runtime:
  permissions:
    contents: read
  uses: msft-contoso-university/contoso-engineering/.github/workflows/runtime-service-pr.yml@<reviewed-40-character-engineering-commit>
  with:
    service: students
    candidate-sha: ${{ github.event.pull_request.head.sha }}
```

Keep the caller's story, build, security and consumer jobs unchanged. Add
`runtime` to its existing always-running required aggregate's `needs` and require
`needs.runtime.result == 'success'`; missing/skipped/cancelled is not success.
Do not add a path filter or `continue-on-error` around the runtime call.
The reusable aggregate also requires both source resolution and integration
to succeed, including complete evidence validation and artifact upload.

The seven-day `runtime-pr-<service>-<sha>-<run>-<attempt>` artifact contains
TRX, pre-build `source-evidence.json`, and, only after complete passing tests,
`runtime-evidence.json`. The JSON binds run ID/attempt, PR number/head SHA,
all four immutable source SHAs, verified checkouts, and actual harness commit;
the final report includes nonzero passing totals and each required case result.
Source evidence is retained if a later build/test fails, but is not itself a
successful runtime result. Evidence contains only source identities and
synthetic test results, never credentials. Checkout credentials are not
persisted, the token is exposed only to the source-resolution API step, and
runtime jobs have no Azure, write or inference permissions. Standard
`GITHUB_TOKEN` cannot read other private repositories: inaccessible peers fail
visibly rather than requesting a broader token or inheriting secrets.

Engineering-only unit tests and workflow lint do not complete the cross-repo
story. After this reusable workflow is reviewed and merged, each service must
pin that reviewed Engineering commit in a real PR, inspect its exact-head
source evidence, and pass all existing hosted checks. An intentionally
incompatible service candidate must visibly fail the actual runtime job and
the caller's required aggregate. Until those hosted positive and negative runs
exist, the new gate is **not operational proof**. No branch protection, release
lock, Azure resource or application authentication change is part of this work.
