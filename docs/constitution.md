# ADLC constitution

1. **Intent before implementation.** A story contains a user benefit, goal,
   boundaries, observable acceptance criteria, verification, affected
   repositories, and risk/rollback. Structure is mechanically checked;
   completeness and product meaning require human acceptance.
2. **Distinct authority.** gh-aw analyzes and requests allowlisted safe outputs.
   Cloud agents propose code and tests. Copilot review advises on implementation.
   Actions enforces deterministic checks. CodeQL and dependency/secret detectors
   supply security evidence. SRE investigates and proposes recovery. Humans
   accept intent, approve releases, merge, and authorize remediation.
3. **No self-approval.** Only a human with repository write access adds
   `ready-for-agent`. The story gate checks the latest label audit event and
   current collaborator permission. It does not prove who controlled a human's
   credential; do not share human credentials with agents.
4. **Fail closed.** Missing tests, unrecognized contracts, API failures, and
   unavailable security or inference services are failures or explicit pending
   work, not successful validation. Required checks must not silently skip.
5. **One writer, bounded work.** Serialize conflicting changes. Pin reusable
   controls and deployment inputs to reviewed commits. Use bounded comments,
   dispatches, retries, and finite deadlines; avoid event feedback loops.
6. **Evidence and learning.** Link story, PR, checks, immutable artifact,
   deployment, incident, and approved correction. Preserve redacted evidence
   across stack teardown. Update regression tests/runbooks after incidents.
7. **Least privilege and privacy.** Public evidence contains synthetic or
   redacted information only. No raw production logs, secrets, broad agent
   credentials, privileged PR runners, or automatic production authority.

These are original implementation rules informed by the
[Agentic SDLC Handbook](https://danielmeppiel.github.io/agentic-sdlc-handbook/),
[GitHub Agentic Workflows](https://github.github.com/gh-aw/),
[Spec Kit](https://github.com/github/spec-kit),
[Anthropic's engineering guidance](https://www.anthropic.com/engineering/building-effective-agents),
[Kiro specs](https://kiro.dev/docs/specs/), and
[Google Conductor](https://github.com/gemini-cli-extensions/conductor).
The handbook is research input, not copied content or an installed framework.
