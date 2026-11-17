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
locks or weaken the check. Runtime inference uses `copilot-requests: write` and
requires organization billing/entitlement. Compilation is not a successful AI
run. Missing entitlement is pending setup, not an operational workflow.

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

The selector only identifies required tests; it does not execute them or
approve a change. Consumer test identifiers, contract paths and their CI
integration must be implemented and verified in each application repository
before this can serve as a release gate. Unknown contract files fail closed.
Changes to this mapping require review by the relevant producer and consumers.

## Authority boundaries

Agents can advise and propose changes, not accept their own specifications,
approve their own pull requests, or deploy. GitHub Actions enforces
deterministic checks, while humans authorize the consequential transitions.
Application repositories own their data, REST contracts, and test execution.
Public issues and evidence must contain only synthetic or redacted data.
