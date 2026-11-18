# Contoso engineering

This repository contains shared controls for the Contoso ADLC demonstration.
The complete Azure environment is **not yet operational**. See
`docs/constitution.md` for the authority boundaries and
[the evidence index](docs/evidence.md) for measured outcomes and remaining gates.

## Accepted intent

Use the ADLC user story issue form. Triage can suggest clarification, but only
a human repository writer may add `ready-for-agent`. PRs link 1-4 accepted
stories on separate `Closes #123` lines (full `owner/repo#123` and canonical
GitHub issue URLs are also supported). The deterministic story gate checks
structure, the label audit actor, and that actor's current write permission.
It does not prove semantic quality or a human credential's exclusive control.

Application CI can consume `.github/actions/story-gate` at a reviewed full
commit SHA with an explicit read-only `github-token` input. Grant caller jobs
`contents: read`, `issues: read`, and `pull-requests: read`; do not check out or
execute untrusted PR code in a privileged context.
Engineering's own PR story check loads policy from the trusted base commit,
separate from candidate-code unit tests. `Required checks` rejects a skipped
story check on PRs. Policy/workflow changes have explicit code ownership.
PR description edits re-run the gate. If a linked issue or its acceptance
changes afterward, re-run the checks before review/merge: a completed CI run
is evidence for the issue state it observed, not a continuous authorization.

## Agentic workflows

`issue-triage.md` requests bounded clarification/comments and advisory labels.
`acceptance-review.md` requests COMMENT-only acceptance/impact reviews, distinct
from Copilot implementation review. Neither can accept a story, approve a PR,
dispatch a deployment, or merge.

`cross-repo-tracking.md` is human-dispatched with an explicit component issue.
It reads only the four allowlisted application repositories and creates at most
one central reference, with a fixed source-identity title and handler-enforced
title deduplication. No cross-repository write credential is needed because the
only writer targets this central repo; component-side automatic forwarding and
bidirectional updates still require a separately scoped GitHub App.

The pinned Linux compiler in `compile-agentic.yml` generates locks and rejects
uncommitted generated output. Bootstrap compilation may fail this final check
until its real `agentic-locks` artifact is reviewed and committed; do not handwrite
locks or weaken the check. Runtime inference explicitly uses personal/seat
billing (`copilot-requests: none`), not organization-billed Actions tokens.
Compilation is not a successful AI run. Missing credentials or entitlement
remain pending setup, not an operational workflow.

### Personal Copilot inference

The maintainer must supply a fine-grained PAT owned by their own Copilot-enabled
user account, not the organization. Under **Account permissions**, grant only
**Copilot Requests: Read**. Do not grant repository permissions for inference.
Choose a short expiration appropriate for the disposable demonstration.

Create it in [GitHub personal token settings](https://github.com/settings/personal-access-tokens/new?name=COPILOT_GITHUB_TOKEN&description=GitHub+Agentic+Workflows+-+Copilot+engine+authentication&user_copilot_requests=read)
and store it directly as the organization Actions secret
[`COPILOT_GITHUB_TOKEN`](https://github.com/organizations/msft-contoso-university/settings/secrets/actions).
For a new secret, use **Selected repositories** and allow
`contoso-engineering`, where these inference workflows run. Add another
repository only when it needs inference. Do not remove unrelated consumers
from an existing shared secret without reviewing their dependencies.
Never paste its value into an issue, chat, source file, log, or command argument.
The maintainer must complete token creation and secret entry; agents do not
retrieve existing CLI credentials or handle the token.

An allowed repository inherits the organization secret through the same
`secrets.COPILOT_GITHUB_TOKEN` reference; no value needs to be copied into a
repository secret. A repository-local secret with that name overrides the
organization value. A repository-only secret listing does not show inherited
organization secrets, so an empty listing alone does not establish that the
workflow lacks a credential.

An active personal Copilot entitlement is required; usage belongs to that
account's allowance and billing limits, even when the secret is stored by the
organization. GitHub App and OAuth user-session tokens
are not supported for this inference secret. Adding the secret without removing
`copilot-requests: write` would leave organization billing active and ignore it.

The compiler binds the PAT only to Copilot inference. GitHub tools and safe
outputs retain their separate least-privilege Actions credentials. Do not add
repository access to the inference PAT to repair cross-repository tools; review
any separately required GitHub App/read credential independently. Keep the
three workflows paused until the generated locks are committed, native
checks pass, and the secret is present. Then authorize one bounded pilot;
do not enable all event triggers or claim working inference from compilation.

The actual triage attempt reached its inference provider and received HTTP 403;
the precise authorization cause is unresolved. All three inference workflows
are now natively paused (`disabled_manually`) to prevent automatic retries.
Do not re-enable or rerun them until valid provider authorization is established.
Compilation, deterministic CI and code scanning remain separate and enabled.

The compiler also emits optional `agentics-maintenance.yml`; this repository
does not install that autonomous maintenance workflow. CI verifies every new
or changed generated `*.lock.yml`, not unrelated compiler side files.
The framework's native repository-role activation check restricts triage to
trusted writers; public issue creation alone does not authorize inference.

The [source baseline](docs/baseline.md) records initial static observations and
explicitly identifies characterization work still required.

## Contract impact selection

`contracts\dependencies.json` is the proposed authoritative mapping from API
contract files to consumer test identifiers. Run the selector from this
directory, for example:

```powershell
python tools\contract_impact.py --repository contoso-students --changed-file contracts\students.openapi.yaml
python -m unittest discover -s tests -v
```

The selector alone does not execute tests or approve a change.
`tools/consumer_checks.py` plans all mapped consumers on every producer check,
including implementation-only response changes. It rejects missing/unmapped
contracts and mutable or absent consumer pins. `contracts/consumer-candidates.json`
pins the current **unapproved candidates**, not production releases.

The read-only reusable consumer workflow downloads actual HTTP JSON samples
from the calling producer's exact run, SHA and attempt, then tests the pinned
consumer's real parsing/mapping code. Tests reject breaking required fields,
missing sample categories and malformed inputs; they do not merely validate old
fixtures against a permissive new schema. The result gate requires nonzero
passing TRX cases with no skipped/failed tests. This is offline payload
compatibility, not proof of live Entra, private routing or distributed behavior.

Call the reusable workflow at a full reviewed SHA after successful producer SQL
tests have uploaded `producer-response-samples-<sha>-<attempt>`; include the
caller's resulting job in its always-running aggregate. No inherited secrets,
Azure access, repository writes, model requests or cross-repo dispatch token are
needed. Candidate checks cannot authorize promotion. Changes to the mapping
and consumer pins require producer/consumer review.

## Whole-stack service PR integration

The [runtime harness contract](tests/RuntimeIntegration/README.md#service-pull-requests)
documents the read-only `runtime-service-pr.yml` reusable workflow. Each service
supplies its identity and exact PR-head SHA; the other three `main` branches
are resolved to full commits before restore/build/test and all four actual
checkouts are verified. Complete, non-skipped runtime results and source/run/
harness evidence are required. The existing frozen-candidate runtime workflow
and consumer checks remain separate and unchanged. Service callers must pin a
reviewed Engineering commit and require the runtime result alongside their
existing gates; local validation alone is not hosted whole-stack proof.

## Authority boundaries

Agents can advise and propose changes, not accept their own specifications,
approve their own pull requests, or deploy. GitHub Actions enforces
deterministic checks, while humans authorize the consequential transitions.
Application repositories own their data, REST contracts, and test execution.
Public issues and evidence must contain only synthetic or redacted data.
