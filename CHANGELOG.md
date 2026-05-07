# Changelog

All notable changes to S.A.M.U.E.L. v2.

## How this file is generated

Phasen-Eintraege (Phase 0a - Phase 13) werden manuell beim Phasen-
Abschluss ergaenzt. **Issue-basierte Eintraege ab Phase 14** werden
automatisch ueber das CLI generiert (#163):

```bash
# Default: alle Eintraege seit dem letzten Tag
samuel changelog

# Seit einem bestimmten Tag oder Phasen-Marker
samuel changelog --since v2.1
samuel changelog --phase 13           # mappt auf Tag 'phase-13-complete'

# In Datei schreiben statt stdout
samuel changelog --out CHANGELOG_DELTA.md

# Zusaetzlich als Kommentar zu einem Tracking-Issue posten
samuel changelog --phase 13 --post-to-issue 250
```

Der Aggregator parst conventional-commit-Subjekte (`feat`, `fix`,
`refactor`, `perf`, `docs`, `chore`, ...) zwischen Start-Revision und
HEAD, gruppiert per Issue-Ref `(#NNN)`, und uebergibt das Ergebnis an
den bestehenden ``ChangelogCommand``-Handler. Commits ohne Issue-Ref
werden uebersprungen — die Repo-Konvention verlangt
`<type>(scope)?: <title> (#<issue>)`.

## [2.0.0-alpha] - 2026-04-17

### Phase 0a: Vorarbeiten
- Pre-commit hooks und Test-Konventionen

### Phase 0b: Shared Kernel
- Event-Bus, Commands, Config, Ports, Types

### Phase 1: Audit-Trail
- JSONL-Audit-Sink mit Rotation und Correlation-IDs

### Phase 2: SCM-Port
- IVersionControl, GiteaAdapter, IAuthProvider

### Phase 3: LLM-Port
- ILLMProvider, CircuitBreaker, SanitizingAdapter

### Phase 4: Planning-Slice
- PlanIssueCommand, 3-Stufen LLM-Qualitaetskontrolle

### Phase 5: Implementation-Slice
- IPatchApplier-Registry, Resume mit WorkflowCheckpoint

### Phase 6: PR-Gates-Slice
- 14 PR-Gates, config/gates.json

### Phase 7: Evaluation-Slice
- Eval-Score-History, Baseline-Threshold

### Phase 8: Watch, Healing, Dashboard + restliche Slices
- 23 Slices komplett, Semaphore-kontrollierte Parallelitaet

### Phase 9: Aufräumen
- v1-Dateien entfernt (commands/, plugins/)
- v1→v2 Mapping-Test
- Sequence-Validator

### Phase 10: Server-Hook + Flexibilität
- Gitea pre-receive Hook
- GitHubAdapter + GitHubAppAuth
- IQualityCheck Registry (Python, TypeScript)
- Skeleton-Builder (Python, TypeScript, Go, SQL, Config)

### Phase 11: Compliance
- PromptSanitizer (PII-Scrubbing)
- TransferWarning (Drittland-Transfer DSGVO)
- AI-Attribution-Trailer (EU AI Act Art. 50)
- DSGVO VVT, AI Act Technical Documentation

### Phase 12: Hardening
- Dockerfile + docker-compose.yml
- pyproject.toml mit allen Extras
- TLS-Verify konfigurierbar
- MetricsMiddleware

### Phase 13: Vergessenes & Konzeptfehler
- E7 Code-Injection Fix (AC-Tag Sanitization)
- M3 Semaphore-Leak Fix
- OpenRouter Pricing Integration
- 6 neue Events, 4 Config-Bereiche externalisiert
