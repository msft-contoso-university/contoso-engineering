# Contoso engineering

This repository will contain the shared, reviewed controls for the Contoso
ADLC demonstration. The environment and its agentic workflows are **not yet
operational**.

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
