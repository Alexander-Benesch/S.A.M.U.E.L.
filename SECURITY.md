# Security Policy

## Supported Versions

| Product line | Status |
|---|---|
| `2.0.0a29` — Latest published alpha with a verified release manifest | Fresh OCI installation independently verified; #989 project/preflight/readiness and #980 verifier-budget fixes included; full process isolation and Golden-D0 remain unqualified; no production support promise |
| Earlier alphas | Superseded; no current installation recommendation or separate backport promise. [Historical release statuses](docs/archive/reader-history-2026-10-12/EDITORIAL_CONTEXT.md#security-release-statuses). |
| Unreleased `main` | Development fixes; no separate backport promise |
| 1.x | Archived; not supported |

New test installations use the latest published alpha candidate and its verified
release manifest. Earlier installation recommendations are superseded; their original evidence
is retained in the historical release statuses linked above.
No complete functional/D0 qualification or production support promise is
implied by publication or a successful installation smoke. See the
binding [versioning and support policy](docs/VERSIONING.md).

<details>
<summary>Historical release references</summary>

The [original release statuses](docs/archive/reader-history-2026-10-12/EDITORIAL_CONTEXT.md#security-release-statuses)
retain these distinctions: `2.0.0a15` — Historical alpha with retained partial evidence,
no current installation recommendation; `2.0.0a7` and earlier published alphas —
superseded, no separate backport promise; `v2.0.0a1` — audit tag, no published release.

</details>

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** create a public GitHub/Gitea issue
2. Send details to the repository owner via private message
3. Include: description, steps to reproduce, potential impact
4. Expected response time: 48 hours

## Security Measures and Current Limits

S.A.M.U.E.L. separates registered mechanisms from demonstrated enforcement.
The machine-readable source and generated human view are
[`docs/capabilities/control-matrix.json`](docs/capabilities/control-matrix.json)
and [`docs/CAPABILITY_MATRIX.md`](docs/CAPABILITY_MATRIX.md). The matrix is
checked in CI against runtime registries, shipped profiles, workflow commands,
proof references, active claims, and a digest of the audited sources.

The following implemented mechanisms have bounded code or regression evidence.
Their limits remain part of each claim; the list is not a deployment, isolation
or regulatory qualification:

- **Installed CLI provenance boundary** — supported operator, systemd and
  container paths invoke the installed `samuel` console script. A regression
  test runs it from an untrusted working directory containing a colliding
  `samuel` package and verifies that the foreign package is not imported.
  `PROJECT_ROOT` and the working directory are not product-code or build-
  identity authorities.
- **Commit-bound PR evaluation** — the local gate run uses one immutable
  repository/base/head/contract/policy subject and fails closed on incomplete
  or oversized diffs.
- **Commit-bound baseline secret scan** — the always-on `diff_secret_scan`
  external gate inspects added lines in that complete candidate diff and
  blocks findings or scanner errors before a PR can be reported as created.
- **Advisory prompt-injection signal** — nine normalized phrase/role indicators are evaluated
  on each Planning, Implementation, Healing and Review prompt before its LLM call. Evidence is bounded and
  correlated; the signal is deliberately not presented as an injection
  boundary.
- **Action-bound Git policy** — `git push --force` and `git push -f` are
  rejected on S.A.M.U.E.L.'s core Git execution path before subprocess launch.
- **Repository-bound Git transport credentials** — every managed HTTP fetch or
  push uses the same `IGitTransportAuth` port, validates the configured
  endpoint and repository path, and delegates the token only through the
  installed absolute `GIT_ASKPASS` helper. Tokens in argv/`http.extraHeader`,
  remote URLs or persistent Git configuration are prohibited; interactive,
  system/global-config and credential-helper fallbacks are disabled. Local Git
  and candidate processes do not receive the askpass values (#729).
- **Project-root-bound implementation patches** — before applying any patch
  from one model response, the reference worker resolves every structured or
  textual target to a canonical path below the resolved project root. Absolute,
  traversal and escaping-symlink targets block the complete loop before its
  first write. Every `.git` path component and Git's effective absolute git,
  common, index and object paths are also reserved, including linked/separate
  git dirs and effective `GIT_*` overrides. Evidence contains only bounded
  reason codes and counts; ordinary dotfiles remain versionable. This is a
  filesystem-target boundary, not a general process sandbox (#600, #603).
- **Mutation-free rejected JSON patches** — JSON search/replace and line-range
  candidates are built in memory and parsed before the visible write. A
  validation rejection preserves the existing file and retry source; write-
  time I/O failures remain covered by the process-local loop transaction, not
  by a general filesystem-atomicity claim (#601).
- **Worktree-bound candidate lifecycle** — implementation and healing mutate a
  run-/branch-bound linked worktree outside the target checkout and runtime
  state; Gate 11 uses the detached verification profile of the same manager.
  Local registry booking, POSIX locks, Git's branch/worktree exclusion,
  quarantine and controlled prune prevent two processes from silently owning
  the same branch or deleting unresolved evidence. Parent/tree-bound
  `commit-tree` plus an atomic `update-ref` CAS makes inherited repository
  hooks non-authoritative. This is checkout containment, not a filesystem,
  process, user, network or resource sandbox (#618/#619).
- **Bound restart finalization** — only persisted `commit_pending`,
  `push_pending`, `gates_pending` and `pr_pending` states are resumable. A
  takeover obtains the existing run-worktree OS lock before an expired
  Authority-State lease, then revalidates repository, issue/run, branch/base,
  workspace, contract, gate policy, schemas, signing policy, index/tree/HEAD
  and remote effects. Foreign or ambiguous state is quarantined without
  reset, force-push or silent adoption. Reconcile blocks all automatic resume;
  this is finalization recovery, not LLM-call recovery (#633).
- **Pre-write Python syntax validation** — complete WRITE, search/replace and
  line-range candidates all pass the same local `ast.parse()` hook before
  directory creation or write. A rejected unchanged target is released from
  the precautionary loop snapshot so terminal rollback does not rewrite its
  metadata. Gate 9 remains the later commit-bound syntax authority (#606).
- **Profiled PR-gate registry** — 13 registered functions run as required or
  advisory according to shipped configuration. Registration and `required`
  status do not by themselves prove control depth; see the per-control matrix.
- **Commit-bound contract scope** — required Gate 7b checks every canonical
  changed path from the immutable comparison against Acceptance Contract
  Schema v2. Optional architecture expansion is explicit, derives only from
  `config/architecture.json`, and is part of the bound policy digest.
- **Conditional PII scrubbing** — configured patterns are replaced in user
  messages only when `pii_scrubbing.enabled=true`.
- **Conditional HMAC integrity** — webhook and audit-chain verification require
  their respective keys. The optional context HMAC currently has no consuming
  verifier.
- **Server-enforced Gitea merge path** — on the audited repository, native
  branch protection rejects direct, force and deletion updates to `main`,
  requires exactly the configured `SCM_REQUIRED_STATUS_CONTEXT` for the
  current PR head, and blocks administrator merge override. If absent, the
  visibly reported shipped default is `CI / lint-and-test (pull_request)`.
  `samuel doctor` treats an invalid expectation and a missing, unreadable or
  deviating rule as a release blocker. This is an operator-controlled property
  of each installation, not a portable code-only guarantee.
- **Local dashboard identity boundary** — `config/auth.json` selects exactly
  one access mode. Legacy mode fails startup without its API key; local mode
  never accepts that key as fallback. Argon2 password hashes, non-hierarchical
  roles, opaque instance-bound sessions, CSRF validation, explicit automation
  permissions, fresh reauthentication and durable revocation share the
  existing SQLite authority/witness lifecycle. Restore forces local recovery.
  Passwords, raw sessions, CSRF values and raw automation tokens are excluded
  from logs and diagnostic payloads. This is a bundled standalone reference
  provider, not an IAM, OAuth, PKI or multi-tenant platform (#422/ADR-0422).
- **Audit events and correlation IDs** — emitted coverage is documented per
  mechanism. The pull-only Gitea SCM-check reader stores only a bounded
  projection in the existing observation store and marks every assessment as
  advisory with `authority=none`; this is not a required Evidence Envelope.
- **Passive health/readiness projection** — viewer status and dashboard health
  read bounded instance- and time-bound projections and perform no provider
  probes. Active self-checks require `RUN_PROVIDER_PROBES`. Doctor and audit
  verification remain separate authorities for their own facts; missing,
  expired or restored evidence never becomes a pass. Stored summaries exclude
  credentials, provider responses and audit payloads (#693/ADR-0693).
- **Circuit breaker and retry/fallback adapters** — limit repeated provider
  failure; they do not sandbox an LLM worker.
- **Container release supply-chain contract** — the base OCI index and
  `linux/amd64` manifest are digest-bound; build and runtime dependencies use
  hash-checked locks whose declared inputs are checked in CI. A release
  manifest may record an image only after OCI/runtime identity checks and a
  fresh Compose health/dashboard smoke of the pushed digest. The registry is
  operator-selected and not a Gitea dependency of the product.

Known security-relevant gaps:

- `python -m samuel` cannot enforce package provenance from an untrusted
  working directory because Python selects the package before S.A.M.U.E.L.
  code runs. It is not a supported operating path; explicit `PYTHONPATH`
  manipulation, a replaced console script or a compromised installation
  remain operator/supply-chain boundaries outside this control.

- New alpha installations use the latest published manifest-bound release.
  Installation, component verification, full functional qualification, process
  isolation and Golden-D0 are separate claims; their current evidence and
  remaining scope are recorded in [CURRENT_PRODUCT_STATUS](docs/status/CURRENT_PRODUCT_STATUS.md).
  Earlier a15 evidence is preserved as
  [HISTORICAL / AUDIT_EVIDENCE](docs/archive/A15_REFERENCE_EVIDENCE_2026-09-21.md).

- Built-in secret detection is a bounded baseline: high-confidence assignment,
  bearer, GitHub/API-key and PEM signatures block; JWT shape and AWS access-key
  IDs are advisory. Broad and entropy-based coverage still belongs in a
  specialized scanner. The #520 adapter reads Gitea SCM-check facts only; it
  does not ingest SARIF or promote third-party scanner findings.
- External SCM-check evidence is untrusted input. Responses are size-bounded,
  raw job logs and arbitrary payload text are discarded, identities and full
  SHAs are validated, and missing or contradictory facts remain explicit. A
  green provider status, TLS, runner labels, normalization or later trust
  configuration never upgrades a stored #520 observation to Required
  authority. Request-bound verification and trusted execution remain #679.
- The public `samuel.extensions` boundary accepts only closed, size-bounded
  JSON contracts for `documentation.static_claims` 1.0. It rejects symlinks,
  duplicate keys, traversal, unknown fields, incompatible versions and
  request/result drift. The contract contains no credentials and remains
  advisory. An external process is not trusted or sandboxed merely because it
  uses this boundary; installation and manifest presence grant no authority.
- `documentation.inventory.v1` additionally requires exact policy coverage,
  a bound consumer-tool digest and byte-for-byte Git blobs from the requested
  full HEAD. Before publication the verifier reuses the shipped secret-shape
  policy and blocks private-network or local-credential-path signals without
  copying matched values. The projection contains metadata and immutable
  source links, not a truth assertion about free prose. Git publication uses
  the existing remote marker, non-force push, no-op and receipt-reconciliation
  path. The reference producer runs with a cleared environment and rejects
  known credential variables without exposing their values; it never receives
  the publisher credential.
- Prompt-risk matching covers the four shipped worker prompt paths with nine
  patterns and bounded Unicode normalization, but paraphrases and confusables
  outside that small skeleton remain bypasses. Prompt headers are advisory
  model-layer instructions; generic marker echo was deliberately rejected as
  an unreliable signal.
- Command policy protects only the core Git execution path against the two
  force-push spellings and `git reset --hard`. It is not a general sandbox or
  tool-call policy.
- The existing `IAuthProvider` retains the HTTP Git token in the trusted
  S.A.M.U.E.L. runtime and an environment-backed setup may expose it there as
  `SCM_TOKEN`; the token additionally exists in the network Git child's
  environment for the duration of that operation. The transport adapter adds
  no persistent copy. The tested reference boundary excludes
  argv, remote/config persistence, logs and candidate children, but does not
  prevent another process under the same OS account from reading runtime or
  child process data such as platform-dependent `/proc/<pid>/environ`.
  It is not a complete multi-user credential-isolation claim.
- Gate 9 reads changed Python blobs from the exact candidate head and records
  CPython/AST version evidence. It is still syntax-only, not lint/type/test/CI
  evidence; non-Python changes and confirmed deletions are `not_applicable`.
- Active static preflight gates 7b, 7, 8, 9, 13a and 13b execute before any candidate
  IMPORT or TEST process. A required preflight failure records every remaining
  internal and external gate as `skipped_precondition` (`executed=false`,
  `passed=null`), emits one complete bound observation and never starts
  candidate verification or healing. This reduces unnecessary execution but
  is not a sandbox.
- Gate 11 consumes schema-validated acceptance evidence bound to repository,
  base/head SHA, contract and policy. Its automatic verifier remains limited
  to the documented AC tags; manual criteria require a matching human SCM
  receipt and otherwise remain `manual_pending`.
- TEST runner command, timeout and runner-policy version come from the
  bootstrap-bound control-plane `config/eval.json`; candidate manifests can
  select only fixed built-in templates. The runner-policy subset is included
  in the EvaluationSubject policy digest. This prevents candidate policy
  override but is not a process, filesystem or network sandbox, and candidate
  test code is still executed.
- Candidate IMPORT and TEST children receive only the versioned
  `verifier-sterile.v1` environment allowlist with manager-created HOME, temp
  and XDG directories. Parent SCM/LLM/cloud/signing credentials, Git path
  overrides, askpass variables, `PYTHONPATH` and shell-profile variables are
  not inherited. The profile is recorded in criterion evidence and the
  EvaluationSubject policy digest. A same-user child may still access other
  host-readable files or process data (including platform-dependent `/proc`),
  and network/resource boundaries remain unsandboxed.
- Quarantined worktrees may contain LLM-written code and test artifacts. They
  live under the separately configured `agent.workspace.work_dir`, are not
  part of state backups, are never silently pruned, and block new runs when
  their configured count or capacity ceiling is reached. Operators inspect
  them with `samuel workspace list|inspect --json` before explicit cleanup.
  The 168-hour deadline is an operator-review target, not automatic deletion;
  only a reasoned `workspace discard` makes reviewed evidence terminal.
- Gitea branch protection is external mutable state. The audited repository is
  protected, while every other installation must configure and revalidate the
  same rule before making the merge-path claim.
