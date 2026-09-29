# Contributing to S.A.M.U.E.L.

## Setup

```bash
git clone https://gitea.example.invalid/owner/S.A.M.U.E.L.git
cd S.A.M.U.E.L
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Development Workflow

1. Create a branch from `main`: `git checkout -b feat/my-feature`
2. Write code + tests
3. Run tests: `.venv/bin/python -m pytest tests/ samuel/ -q`
4. Run the repository-wide lint and format checks:
   `.venv/bin/ruff check . && .venv/bin/ruff format --check .`
5. Create PR — the 15 registered PR gates will check your code according to the active profile

## Versioning and releases

The binding policy is [`docs/VERSIONING.md`](docs/VERSIONING.md). Do not create,
move, or repurpose product tags while preparing an ordinary change. Product
tags use canonical PEP-440 versions with a `v` prefix; historical
`phase-*-complete` tags are not releases. The executable create-only procedure,
pre-/post-tag gate, artifact manifest and abort rule are defined in
[`docs/VERSIONING.md`](docs/VERSIONING.md). Ordinary changes must not invoke
`tools/release_gate.py` as permission to tag an unmerged branch.

If a release is intended as the next Golden-D0 candidate, the exact final
development commit must first satisfy the pre-release Golden-Rehearsal exit in
[`docs/OPERATING_RULES.md`](docs/OPERATING_RULES.md) R24. Findings follow the
ordinary issue → regression → PR → CI → human-merge workflow and produce a new
candidate commit; they do not trigger an intermediate product release by
themselves. Impact-based retests may preserve earlier attempt evidence only as
development evidence. Before tagging, the final candidate must complete one
full same-binding rehearsal without a product-code change. This rehearsal is
neither publication nor formal Golden-D0 qualification.

Container dependency or base-image changes must keep
`containers/lock-policy.json`, both `requirements-container*.lock` files and
the Dockerfile consistent. Run `python tools/container_release.py check`; the
reviewed update, rollback and registry-neutral publication procedure is
[`docs/CONTAINER_RELEASE_OPERATIONS.md`](docs/CONTAINER_RELEASE_OPERATIONS.md).
Registry credentials and operator `.env` files never belong in the repository.

The external Gitea runner is operated according to
[`docs/CI_RUNNER_OPERATIONS.md`](docs/CI_RUNNER_OPERATIONS.md). CI workflows
must use the repository-specific runner label and full action commit SHAs;
moving `ubuntu-*` labels and mutable action major tags are not accepted as
release evidence.

### Documentation acceptance

Every issue includes documentation consistency in its acceptance contract.
Before closing it, search all affected active documentation and update claims,
operating instructions, and references to this or dependent issues in the same
change. The completion comment names the checked and changed files and the
exact commit.

“No documentation change required” is acceptable only with the documented
search scope and a concrete reason. Files under `archive/` remain historical
snapshots and are not silently rewritten to match current behavior.

Maschinenlesbare Laufzeitfakten werden nicht als zweite manuelle Wahrheit
kopiert. `python tools/control_matrix.py check` prüft Capability-Matrix,
Dokumentklassifikation, abschnittsbezogene Quellenbindungen, generierte
Runtime-Referenz, ADR-Index und lokale Dokumentverweise. Geänderte gebundene
Quellen müssen entweder die deterministisch generierte Referenz verändern oder
eine ausdrücklich benannte manuelle Abschnittsprüfung auslösen.

### Capability boundary acceptance

Before implementing a new or materially expanded capability, the issue must
name the smallest user-visible path, existing implementations/tools, core
semantics, one authoritative decision source, required permissions, explicit
non-goals, and the real reference-installation evidence that will prove the
result. For an exchangeable non-core capability, name only the actually needed
bundled-reference and external-provider levels; do not build missing levels in
advance. Generalize beyond the narrow domain port only for a second real
adapter/use case or an explicit security/authority need. Producers and
providers receive no ambient authority, and self-mode changes to core remain
ordinary candidates rather than self-authorized runtime updates. See
[`ADR-0678`](docs/adr/0678-product-boundary-and-integration-profile.md),
[`docs/OPERATING_RULES.md`](docs/OPERATING_RULES.md) R21–R24 and the
copy-ready [handover prompt](docs/PRODUCT_BOUNDARY_HANDOVER_PROMPT.md).

## Architecture Rules

- **No cross-slice imports** — slices only import from `samuel.core.*`
- **No direct adapter usage in slices** — use Ports (ABCs from `samuel.core.ports`)
- **Tests live with their slice** — `samuel/slices/<name>/tests/test_handler.py`
- **One event per state change** — events are published via the Bus

## Code Style

- Python 3.10+, type hints everywhere
- `ruff` for linting and formatting
- No comments unless the WHY is non-obvious
- Commit messages: `feat|fix|docs|test(scope): description`

## Tests

```bash
# All tests
python -m pytest

# Single slice
python -m pytest samuel/slices/planning/tests/

# Architecture validation
python -m pytest tests/test_architecture_v2.py
```
