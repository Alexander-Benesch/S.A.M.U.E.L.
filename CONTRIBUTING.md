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

Before the first mutation, follow the existing
[Coding-Agent entry](.claude/CLAUDE.md#vor-der-ersten-mutation): establish the
current repository and issue/comment/PR state, identify integrated work and
remaining scope, then select the applicable contracts, impact path and tests.
The same instructions define routine autonomy, maintainer escalation and
bound completion claims. Normal development does not require a Golden PASS.

1. Create a branch from `main`: `git checkout -b feat/my-feature`
2. Write code + tests
3. Run tests: `.venv/bin/python -m pytest tests/ samuel/ -q`
4. Run the repository-wide lint and format checks:
   `.venv/bin/ruff check . && .venv/bin/ruff format --check .`
5. Create PR — the 13 registered PR gates will check your code according to the active profile

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
For every documentation-relevant product, configuration, contract, API,
workflow or agent-rule change, review the documentation impact, including new
features without an existing document or source binding. Update affected
claims, operating instructions, source bindings and checks in the **same PR**
as the change. This includes changed effects with unchanged interfaces: defaults,
permissions, states, errors, recovery and authority boundaries need review.
The completion comment names the checked and changed files and the exact commit.

“No documentation change required” is acceptable only with the documented
search scope and a concrete reason. Files under `archive/` remain historical
snapshots and are not silently rewritten to match current behavior.

Maschinenlesbare Laufzeitfakten werden nicht als zweite manuelle Wahrheit
kopiert. `python tools/control_matrix.py check` prüft Capability-Matrix,
Dokumentklassifikation, abschnittsbezogene Quellenbindungen, generierte
Runtime-Referenz, ADR-Index und lokale Dokumentverweise. Geänderte gebundene
Quellen müssen entweder die deterministisch generierte Referenz verändern oder
eine ausdrücklich benannte manuelle Abschnittsprüfung auslösen.

Before PR review, compare the actual committed base and candidate:

```bash
python tools/control_matrix.py impact --base <BASE-SHA> --head <HEAD-SHA>
```

This read-only advisory report lists **every changed tracked path**, even when
no source binding exists. It includes possible bindings from both commits and
partial structural hints for literal CLI arguments, API strings and JSON
field paths. It does not inspect uncommitted or untracked files, print config
values, execute product modules, or prove semantic coverage. Review dynamically
constructed surfaces and changed effects even when no structural hint changes.
Malformed or unsupported source extraction remains visible for manual review.

In the existing PR description or linked issue evidence, record the compared
commits, reviewed paths and effects, affected documentation/bindings/checks,
and the updates made in this PR. For each group needing no update, give the
search scope and concrete source-aware reason. Matching bindings, refreshed
digests and an empty structural delta do not waive this decision. Necessary
generator or binding adjustments land before or with the affected migration.

`impact` without `--base` retains the existing working-tree section-drift
report. `check` and `render` retain their existing contracts. The commit report
does not add a blocking CI requirement; any new blocker needs demonstrated
need, positive/negative regressions and explicit maintainer approval.

### Fachliche Bilder und Diagramme

Die Documentation acceptance gilt auch für Screenshots, SVGs und andere
fachliche Bilder. Vorhandene Pflegezuständigkeit bleibt `repository-maintainers`.
Im bestehenden beschreibenden Dokument benennt die Bildunterschrift oder der
zugehörige Abschnitt Aussage/Zweck, Quelle und Stand (Commit, Run oder datierter
realer Screenshot), Aufnahme-/Bereinigungsschritte und sichtbare Grenzen.
Wesentliche Aussagen bleiben als Text zugänglich. Ein Fachdiagramm erklärt einen
Ablauf; es ist kein Nachweis eines tatsächlich ausgeführten Laufs. Historische
Bilder behalten ihre Kennzeichnung und werden nicht als heutige UI ausgegeben.

Der zugehörige manuelle Abschnitt in
`docs/capabilities/document-contract.json` bindet mit den vorhandenen
`sources` sowohl die Bilddatei (`kind: file`, auch PNG/SVG) als auch die
maßgeblichen Code-, UI-, Workflow-, Ausgabe- oder Contractquellen. Geeignete
vorhandene Selektoren begrenzen die geprüfte Quelle; der Eintrag benennt
passende bestehende Proofs. Für neue Bilder und neue bislang ungebundene
Oberflächen gilt derselbe Änderungsreview. Es gibt keinen separaten Bildindex
mit eigener Authority und keinen neuen CI-Blocker.

Bei jeder relevanten Änderung wird im selben PR entschieden, ob Bild, Erklärung,
Quellenbindung oder Prüfung aktualisiert werden müssen. Ein Verzicht benennt
Suchumfang, betroffene Aussage, geprüfte Quelle und konkreten Grund. Der
bestehende commitbezogene `impact`-Report führt auch neue Bildpfade ohne Binding
auf. Der Dateidigest erkennt geänderte gebundene Bytes; Codequellendrift fordert
den manuellen Abschnittsreview. Weder Mechanismus erkennt selbständig, ob ein
Screenshot fachlich vollständig, datenschutzgerecht oder semantisch veraltet
ist. Ein neuer Digest ersetzt diese Prüfung nicht.

Bildverweise durchlaufen den vorhandenen Wiki-Build und Publisher. Die aktuelle
Publikation schreibt Repositoryverweise auf den gebundenen Main-Commit um;
sie kopiert keine separaten Bildbestände in ein zweites Veröffentlichungssystem.
Für Inlinebilder kann der bestehende Publisher mit `--image-url-template` eine
eigene SHA-/Pfad-gebundene Raw-URL verwenden (technische Referenz §24).
Zusätzlich muss die tatsächlich ausgelieferte Darstellung geprüft werden:
Ein normaler Repository-Dateilink ist nicht automatisch eine als Bild ladbare Raw-URL. Bis diese konkrete Darstellung nachgewiesen ist,
bleibt ein korrekt gebundener anklickbarer Bildverweis zulässig; eine gelungene
Inlineanzeige darf nicht behauptet werden. Nach Human Merge aktuelle Contracts,
Wiki-Build/Publikation/Readback und betroffene Bildziele nach bestehendem Verfahren
prüfen. Eine Publikation eines ungemergten Bild-Candidates ist kein Ersatz.

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

- Python 3.12+, type hints everywhere
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
