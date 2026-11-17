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
