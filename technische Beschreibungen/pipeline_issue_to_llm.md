# Pipeline: Issue → LLM-Prompt

Technische Beschreibung jedes Knotenpunkts in der Context-Building-Pipeline.
Ziel: Nachvollziehbarkeit des Ablaufs — wo kommt was her, wo geht es hin,
welche Dateien sind beteiligt, welche Sprachen werden unterstützt,
welche Voraussetzungen gelten.

**Prüfdatum:** 2026-09-01 · **Abgeglichener Commit:**
`53b859467bb28dced6e7208c020b70da4d708e75`.

Der Implementation-Kontext wird pro `ImplementCommand` im zugehörigen
Run-Worktree neu aufgebaut. Er ist Worker-Input vor dem Candidate und deshalb
noch keine `EvaluationSubject`-gebundene Freigabe-Evidence.

---

## Inhalt

1. [Übersichts-Flussdiagramm](#übersichts-flussdiagramm)
2. [Kontextlebenszyklus und Werkzeuggrenzen](#kontextlebenszyklus-und-werkzeuggrenzen)
3. [K1 — Issue-Input (Event + SCM)](#k1--issue-input)
4. [K2 — `iter_project_files()` Datei-Iteration](#k2--iter_project_files)
5. [K3 — `extract_keywords()` Keyword-Extraktion](#k3--extract_keywords)
6. [K4 — `extract_plan_files()` Plan-File-Erkennung](#k4--extract_plan_files)
7. [K5 — Architecture-Context (Rollen + Scopes)](#k5--architecture-context)
8. [K6 — `expand_via_symbol_references()` Transitive Dateien](#k6--expand_via_symbol_references)
9. [K7 — Skeleton-Builders (pro Sprache)](#k7--skeleton-builders)
10. [K8 — `filter_skeleton()` Symbol-Matching gegen Issue](#k8--filter_skeleton)
11. [K9 — `grep_keywords()` Keyword-Suche im Projekt](#k9--grep_keywords)
12. [K10 — `render_files_section()` Smart-File-Load](#k10--render_files_section)
13. [K11 — `build_full_context()` Kontext-Aggregation](#k11--build_full_context)
14. [K12 — `_build_implement_prompt()` Prompt-Assembly](#k12--_build_implement_prompt)
15. [K13 — `validate_context()` Pre-LLM Validator](#k13--validate_context)
16. [K14 — `run_llm_loop()` LLM-Call mit Retry](#k14--run_llm_loop)
17. [K15 — `patch_parser` + Applier](#k15--patch_parser--applier)
18. [K16 — Git-Operationen + `CodeGenerated`-Event](#k16--git-operationen--codegenerated-event)
19. [Anhang: Config-Dateien die die Pipeline steuern](#anhang-config-dateien)

---

## Übersichts-Flussdiagramm

```
                         ┌─────────────────────────┐
                         │ K1  Issue (Gitea-API)   │
                         │ title, body, plan_comm. │
                         └────────────┬────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
           ┌────────────────┐ ┌──────────────┐ ┌──────────────┐
           │ K3 Keywords    │ │ K4 Plan-Files│ │ K5 Arch-Ctx  │
           │ (Stop-Words)   │ │ (Backticks)  │ │ config/      │
           └───────┬────────┘ └──────┬───────┘ │ architecture │
                   │                 │         │ .json        │
                   │                 ▼         └──────┬───────┘
                   │      ┌──────────────────┐        │
                   │      │ K6 Symbol-Ref    │◄───────┤ allowed/blocked
                   │      │ Expansion        │        │ scopes
                   │      │ (sprachagnostic) │        │
                   │      └──────┬───────────┘        │
                   │             │                    │
                   │             ▼                    │
                   │      ┌──────────────────┐        │
                   │      │ K8 filter_skel.  │        │
                   │      │ (Issue × Skel)   │◄───────┤ module_info
                   │      └──────┬───────────┘        │
                   ▼             │                    │
           ┌────────────────┐    │                    │
           │ K9 grep_kw     │    │                    │
           │ (Word-Boundary)│◄───┴────────────────────┤
           └───────┬────────┘    │                    │
                   │             ▼                    │
                   │      ┌──────────────────┐        │
                   └─────►│ K10 render_files │        │
                          │ (smart-load)     │        │
                          └──────┬───────────┘        │
                                 ▼                    │
                          ┌──────────────────┐        │
                          │ K11 build_full_ │◄───────┘
                          │ context          │
                          └──────┬───────────┘
                                 ▼
                          ┌──────────────────┐
                          │ K12 Prompt-Build │
                          └──────┬───────────┘
                                 ▼
                          ┌──────────────────┐
                          │ K13 Validator    │──────► WorkflowBlocked
                          │ OK? ─ nein       │         (Abbruch)
                          └──────┬───────────┘
                           ja    │
                                 ▼
                          ┌──────────────────┐
                          │ K14 LLM-Loop     │──────► TokenLimitHit
                          │ (5 Runden max)   │         WorkflowBlocked
                          └──────┬───────────┘
                                 ▼
                          ┌──────────────────┐
                          │ K15 Patch apply  │
                          └──────┬───────────┘
                                 ▼
                          ┌──────────────────┐
                          │ K16 Git + Event  │
                          │ CodeGenerated    │──────► PR-Gates → PR
                          └──────────────────┘
```

---

## Kontextlebenszyklus und Werkzeuggrenzen

Der Bootstrap stellt einen `IWorkspaceManager` und die gemeinsame
Skeleton-Registry bereit. Vor der ersten Candidate-Mutation wird der im
Acceptance Contract enthaltene `PlanningSourceSnapshot` aus dem neuesten
Plan-Kommentar gelesen. Repository, Issue-Digest und aktueller Remote-Base-Ref
müssen weiterhin zu dessen vollständiger Base-SHA passen. Erst dann wird für
den Run auf genau diesem Commit ein eigener Worktree vorbereitet.
`_handle_in_project()` lädt Issue und den
letzten passenden Plan-Kommentar erneut und ruft anschließend genau einmal
`build_full_context(...)` gegen diesen Worktree auf. Ein zweiter
`ImplementCommand` baut den Kontext erneut; innerhalb des anschließenden
Multi-Round-Loops werden die Ausgangssektionen nicht automatisch vollständig
neu indiziert. Das Modell kann für große Dateien gezielte `SLICE`-Nachfragen
stellen, die jeweils gegen den aktuellen Worktree aufgelöst werden.
Enthält Acceptance Contract v3 eine Klärungsbasis, liest der Handler vor dem
Kontextaufbau außerdem jeden gebundenen Frage- und Antwortkommentar erneut.
Fehlende oder editierte Bodies/Revisionen, ein anderer Akteur, eine späte
Antwort oder eine abweichende Issue-/Base-Quelle blockieren vor dem
Implementation-LLM. Antworttexte werden dabei nicht in Audit- oder
Dashboardpayloads kopiert.

| Werkzeug | Input und Scope | Output/Limit | Fehler- und Trust-Grenze |
|---|---|---|---|
| `iter_project_files` | Run-Worktree; konfigurierte Extensions und Excludes | deterministische Dateiiteration mit Größenlimit | unlesbare/ausgeschlossene Dateien fehlen im Kontext; keine Sicherheitsisolation |
| `extract_keywords` | Issue-Titel, Body und Plan | begrenzte Keywordliste | lexikalisch, nicht semantisch |
| `extract_plan_files` | Backticks/Pfade aus Issue und Plan | nur existierende repositoryrelative Dateien | nicht erkannte Pfade werden nicht erfunden; Vollständigkeit ist heuristisch |
| Architekturauflösung | initiale Plan-Dateien plus `config/architecture.json` | Rollen, globale Constraints, erlaubte/blockierte Expansionsscopes | begrenzt Auswahl; erteilt keine Gate- oder Mergefreigabe |
| `expand_via_symbol_references` | Identifiertext der Plan-Dateien plus Definitionen aus Skeleton-Buildern | begrenzte zusätzliche Dateien; mehrdeutige/noisy Symbole und unpassende Testpfade werden übersprungen | kein AST-Callergraph, kein allgemeiner Import-/Dependency-Graph und keine transitive Vollständigkeitsgarantie |
| `filter_skeleton` | Issue/Plantext, Plan-Dateien und frisch extrahierte Symbole | keyword-/symbolbezogene Signaturen mit Zeilenbereichen | Parser-/Regex-Grenzen der jeweiligen Sprache bleiben sichtbar |
| `grep_keywords` | höchstens die ersten fünf Keywords; konfigurierte Code-Extensions | Wortgrenzen, begrenzte Treffer pro Keyword und 200 Zeichen pro Trefferzeile | nur Context Retrieval; **nicht** das AC-Tag `GREP` und keine Freigabe-Evidence |
| Smart-File-Load | ausgewählte Plan-Dateien | kleine Dateien vollständig; große Dateien als Trefferregionen, begrenzter Header oder Skeleton-TOC | verhindert Blind-Dumps, garantiert aber keine fachlich vollständige Auswahl |
| `SLICE`-Resolver | `Datei:Start-End` aus einer LLM-Folgerunde | max. 200 Zeilen, Pfad innerhalb Worktree, optionaler Skeleton-Hinweis | zielgerichtetes Nachladen, kein allgemeiner Tool-/Shellzugriff |
| Context-Validator | zusammengesetzter Prompt und Sektionen | Präsenz-, Größen- und grobe Tokenprüfung (`len/4`) | blockiert offensichtliche Defizite; beweist weder Modellfähigkeit noch providerexaktes Tokenbudget |

Die ausgelieferten Skeleton-Builder sind: Python über Standardbibliothek-AST;
JavaScript/TypeScript über tree-sitter; Go, SQL und Teile strukturierter
Konfiguration über begrenzte Regex-/Strukturextraktion. Die genaue
Extension-Zuordnung steht in K7 und in
`samuel/adapters/skeleton/registry.py`.

Es gibt kein eigenes „Context erfolgreich“-Event der Implementation.
`tools_loaded`, vorhandene `context_sections` und die Tokenabschätzung werden
als Metadaten des LLM-Aufrufs geführt; ein harter Context-Befund publiziert
`WorkflowBlocked(reason=context_insufficient)`. `CodeGenerated` belegt erst
den erzeugten/committierten Candidate-Pfad. Commitgebundene Acceptance- und
Gate-Evidence entsteht danach, nicht aus dem Prompt-Kontext.

---

## K1 — Issue-Input

**Datei:** `samuel/slices/implementation/handler.py`, Methode `ImplementationHandler.handle`

**Woher?** Drei Quellen:
- CLI: installierter Entry-Point `samuel run <issue_number>` → `cli.py:_cmd_run` publiziert `IssueReady` → WorkflowEngine sendet `ImplementCommand`
- REST-API: `POST /api/v1/issues/{id}/implement` → `adapters/api/rest.py:65`
- Workflow: `autonomous`, `night`, `patch` senden `Implement` bei einem Plan
  ohne Klärungsbasis direkt nach `PlanValidated`. Enthält der Contract eine
  Klärungsbasis, warten auch diese Profile auf `PlanApproved`.
  **`standard`, `watch`, `chat` und `self` warten immer auf
  `PlanApproved`** — also auf die menschliche Freigabe. Das Label
  `status:approved` wird per Webhook oder Watch-Polling verarbeitet; Kommentare
  `ok` beziehungsweise `/approve` ausschließlich über einen eingerichteten,
  signaturvalidierten SCM-Webhook-Ingress. Activity-Polling erteilt keine
  Freigabe. Der Receipt bindet dabei die aktive Plan-Kommentar-ID zusätzlich
  zum Contract-Hash und akzeptiert beim Polling nur ein späteres,
  menschlich attribuiertes Labelereignis. Im `self`-Workflow liegt zusaetzlich
  die Quality-Stufe dazwischen.

**Was passiert im Handler:**
```
cmd = ImplementCommand(issue_number=136, correlation_id=...)
↓
issue = self._scm.get_issue(136)      # Gitea API-Call
comments = self._scm.get_comments(136)
plan_text = comment mit "## Plan" oder "### Akzeptanzkriterien"
```

**Input für die Pipeline:**
- `issue_title: str`
- `issue_body: str`
- `plan_text: str` (kann leer sein)

**Beispiel-Issue:**
```
Title:  CLI: --version Flag hinzufügen
Body:   Die CLI soll einen `--version` Flag unterstützen.
        Version aus `samuel/__init__.py` lesen.
Plan:   ## Plan
        Änderungen in `samuel/cli.py`: argparse action='version'.
```

**Voraussetzungen:**
- SCM-Adapter verdrahtet (`GiteaAdapter` / `GitHubAdapter`)
- ENV: `SCM_URL`, `SCM_TOKEN`, `SCM_REPO`

**Geht an:** K3 (Keywords), K4 (Plan-Files), K11 (build_full_context)

---

## K2 — `iter_project_files()`

**Datei:** `samuel/core/project_files.py`

**Zweck:** Zentrale, sprachunabhängige Datei-Iteration. Ersetzt alle verstreuten `rglob()`-Aufrufe.

**Signatur:**
```python
iter_project_files(
    root: Path,
    *,
    extensions: Iterable[str] | None = None,
    max_size_kb: int | None = None,
    exclude_dirs: Iterable[str] | None = None,
    exclude_files: Iterable[str] | None = None,
    follow_symlinks: bool = False,
) -> Iterator[Path]
```

**Defaults (merged mit User-Angaben):**
- `DEFAULT_EXCLUDE_DIRS` (20 Einträge): `__pycache__, .git, .venv, venv, node_modules, .tox, .mypy_cache, .pytest_cache, dist, build, target, out, bin, obj, data, .cache, ...`
- `DEFAULT_EXCLUDE_FILES`: `package-lock.json, yarn.lock, poetry.lock, Cargo.lock, go.sum, Gemfile.lock, ...`

**Konstanten (importierbar):**
- `CODE_EXTENSIONS` (30+): `.py, .js, .ts, .tsx, .jsx, .go, .java, .kt, .scala, .rs, .rb, .php, .swift, .c, .cc, .cpp, .h, .hpp, .cs, .lua, .sh, .sql, ...`
- `CONFIG_EXTENSIONS`: `.json, .yaml, .yml, .toml, .ini, .env`
- `DOC_EXTENSIONS`: `.md, .rst, .txt, .adoc`

**Sprachen:** Alle — extension-basiert. Kein Parsing.

**Beispiel:**
```python
from samuel.core.project_files import iter_project_files, CODE_EXTENSIONS

for f in iter_project_files(Path("."), extensions=CODE_EXTENSIONS, max_size_kb=50):
    print(f.relative_to(Path(".").resolve()))
# samuel/core/bus.py
# samuel/cli.py
# ...
```

**Wer nutzt das?** K7 (Skeleton-Builder-Scan), K9 (grep_keywords). Nicht für Render direkt.

**Voraussetzungen:** Keine (stdlib only).

---

## K3 — `extract_keywords()`

**Datei:** `samuel/slices/implementation/context_builder.py`

**Zweck:** Extrahiert die wichtigsten Wörter aus Issue-Text. Diese dienen als Input für K9 (Grep) und helfen beim Skeleton-Matching indirekt.

**Algorithmus:**
1. Regex `[A-Za-z_][\w]{2,}` mit `re.UNICODE` — erkennt auch `hinzufügen`, `größe` (Umlaute)
2. Filterung gegen `_STOP_WORDS` (Set mit ~100 Einträgen, en + de)
3. Zählung nach Frequenz
4. Top 12 Keywords zurück

**Stop-Word-Kategorien:**
- Englisch: `issue, task, plan, code, file, the, and, for, ...`
- Deutsch: `soll, muss, wird, der, die, das, ist, mit, ohne, auf, beim, ...`
- Magic: `__init__, __main__, python, samuel` (Projekt-spezifisch)

**Input:** beliebige Text-Argumente (title, body, plan)

**Output:** `list[str]` — sortiert nach Häufigkeit

**Beispiel:**
```python
kw = extract_keywords(
    "CLI: --version Flag hinzufügen",
    "Die CLI soll einen `--version` Flag unterstützen.",
    "## Plan\nargparse action='version'",
)
# ['version', 'cli', 'flag', 'argparse', 'hinzufügen',
#  'action', 'unterstützen', ...]
```

**Sprachen:** Python-Regex mit UNICODE — alle lateinischen Schriften, auch Umlaute/Akzente.

**Geht an:** K9 (`grep_keywords` nutzt die Top-5).

---

## K4 — `extract_plan_files()`

**Datei:** `samuel/slices/implementation/context_builder.py`

**Zweck:** Findet explizit im Issue genannte Dateipfade (via Backtick-Regex).

**Regex:** `(?:^|[\s`'"])([a-zA-Z0-9_/.-]+(?:\.[a-zA-Z]{1,5}))(?=[\s`'\":,)]|$)`

Erfasst Patterns wie:
- `` `samuel/cli.py` ``
- `"samuel/server.py"`
- `config/agent.json`
- `tests/test_x.py`

**Filter:**
- `startswith("/", "http", "./")` → skip (keine absoluten/URL-Pfade)
- `".." in candidate` → skip (keine Parent-Referenzen)
- `len > 200` → skip
- **Datei muss existieren** im `project_root`

**Max Output:** `MAX_RELEVANT_FILES = 8`

**Beispiel:**
```python
body = "In `samuel/cli.py` den Parser anpassen, siehe `samuel/__init__.py`."
extract_plan_files(body, Path("."))
# ['samuel/cli.py', 'samuel/__init__.py']
```

**Sprachen:** Sprachagnostisch — funktioniert für alle Dateiformate mit Extension.

**Geht an:** K5 (Architecture), K6 (Expansion), K10 (render_files_section).

---

## K5 — Architecture-Context

**Dateien:**
- `config/architecture.json` — Konfiguration (user-editierbar)
- `samuel/slices/architecture/handler.py` — `ArchitectureHandler`
- `samuel/slices/implementation/context_builder.py` — Inline-Lader im `build_full_context` (kein Cross-Slice-Import)

**Zweck:** Beschränkt die Kontext-Expansion basierend auf der Rolle der Plan-Files. Verhindert dass ein Dashboard-UI-Issue plötzlich config/ durchsucht.

**Config-Schema (`config/architecture.json`):**
```json
{
  "global_constraints": [
    "Kein Slice importiert einen anderen Slice",
    "Externe Systeme nur über Ports"
  ],
  "modules": [
    {
      "path": "samuel/server.py",
      "role": "dashboard-frontend",
      "description": "HTTP-Server + Dashboard-HTML",
      "constraints": [
        "Keine Backend-Logik hier",
        "Keine Config-Änderungen bei UI-Issues"
      ]
    }
  ],
  "expansion_policy": {
    "dashboard-frontend": {
      "allowed_scopes": ["samuel/server.py", "samuel/slices/dashboard/"],
      "blocked_scopes": ["config/", "samuel/core/", "samuel/adapters/"]
    }
  }
}
```

**Resolution-Logik (`_resolve_expansion_scope`):**
1. Für jede Plan-File: matche gegen `modules[*].path` → sammle `roles`
2. Für jede gesammelte Rolle: merge `allowed_scopes` + `blocked_scopes` aus `expansion_policy`
3. Übergebe als Set an K6 + K9

**Path-Matching:**
- `"config/"` endet mit `/` → präfix-match
- `"samuel/server.py"` ohne `/` → exact oder präfix mit `/`

**Input:** Plan-Files (aus K4)

**Output:** `{"allowed": set[str], "blocked": set[str], "roles": set[str]}` + `module_info: list[dict]` für Prompt-Sektion

**Beispiel:**
```
Plan-File: samuel/server.py
→ Role: dashboard-frontend
→ allowed: {samuel/server.py, samuel/slices/dashboard/, tests/test_server_dashboard.py}
→ blocked: {config/, samuel/core/, samuel/adapters/}
```

**Sprachen:** Sprachagnostisch — reine Pfad-Metadaten.

**Geht an:** K6 (Expansion-Filter), K9 (Grep-Filter), K11 (module_context-Sektion im Prompt).

**Voraussetzungen:** `config/architecture.json` existiert. Wenn nicht: Pipeline läuft ohne Arch-Constraints (degraded mode).

---

## K6 — `expand_via_symbol_references()`

**Datei:** `samuel/slices/implementation/context_builder.py`

**Zweck:** Sprachagnostische Erweiterung der Plan-Files: wenn Plan-File A ein Symbol referenziert, das in File B definiert ist, füge B hinzu.

**Ersetzt v1-Python-only `expand_via_imports` (AST-basiert).**

**Algorithmus:**
1. Baue **Skeleton-Index:** `{symbol_name: [file1, file2]}` über alle Builder (K7)
2. Für jede Plan-File:
   - Lies Inhalt (nur wenn Extension in `CODE_EXTENSIONS | CONFIG_EXTENSIONS`)
   - Extrahiere alle Identifier (Regex `[A-Za-z_][A-Za-z0-9_]{3,}`)
   - Für jedes Identifier: lookup im Index
3. Filter:
   - **Ambiguous-Filter:** Symbol in >1 Files → skip (außer lang genug: ≥6 chars und ≤2 Defs)
   - **Test-Skip:** Tests/Fixtures werden nicht erweitert (außer Quelle ist selbst Test)
   - **Arch-Scope:** blocked/allowed greifen (K5)
4. Max 8 neue Files

**Doc-File-Skip:** README.md/*.txt triggern keine Expansion (würde auf jede Code-Tokens matchen).

**Beispiel:**
```
Plan-Files: samuel/cli.py

cli.py referenziert:
  main                 → definiert in: cli.py (self, skip)
  bootstrap            → definiert in: samuel/core/bootstrap.py [1 Def] → ADD
  ImplementCommand     → definiert in: samuel/core/commands.py [1 Def] → ADD
  handle               → definiert in: 15+ Slices [ambiguous, 4 chars] → SKIP
  register             → definiert in: 5+ Slices [ambiguous] → SKIP

Result: cli.py + bootstrap.py + commands.py
```

**Sprachen:** Alle, die einen `ISkeletonBuilder` haben (K7). Kein Parser-spezifischer Code.

**Voraussetzungen:** Mindestens 1 Skeleton-Builder für die Plan-File-Sprache.

**Geht an:** K8 (filter_skeleton), K10 (render_files_section).

---

## K7 — Skeleton-Builders

**Dateien:**
- Port: `samuel/core/ports.py` → `ISkeletonBuilder`
- Registry: `samuel/adapters/skeleton/registry.py` → `SKELETON_BUILDERS: dict[ext, builder]`
- Implementierungen: `samuel/adapters/skeleton/{python_ast, tree_sitter_ts, tree_sitter_go, sql_builder, config_builder}.py`

**Zweck:** Extrahiert Symbol-Struktur (Funktionen, Klassen, Methoden, Module-Variables, Config-Keys) aus Dateien — sprach-spezifisch.

**Interface:**
```python
class ISkeletonBuilder(ABC):
    supported_extensions: set[str]

    @abstractmethod
    def extract(self, file: Path) -> list[SkeletonEntry]: ...
```

**SkeletonEntry:**
```python
@dataclass
class SkeletonEntry:
    name: str
    kind: str  # "function", "class", "method", "variable", "key", "type", ...
    file: str
    line_start: int
    line_end: int
    calls: list[str] = []
    called_by: list[str] = []
    language: str = ""
```

**Registrierte Builders:**

| Ext | Builder | Kind-Werte |
|---|---|---|
| `.py` | `PythonASTBuilder` (AST) | function, class, method, variable |
| `.ts/.tsx/.js/.jsx` | `TreeSitterTSBuilder` | function, class, method, interface, type |
| `.go` | `GoRegexBuilder` | function, method (`Struct.Method`), struct |
| `.sql` | `SQLBuilder` | view, procedure, index |
| `.json/.yaml/.yml/.toml` | `StructuredConfigBuilder` | key |

**Fallback-Verhalten:**
- Python: AST falls kein Tree-sitter → immer verfügbar (stdlib)
- TS/JS: Tree-sitter (optional pip install `tree_sitter_typescript`); ohne Tree-sitter: leere Liste
- Go: Regex-basiert (keine externe Abhängigkeit)

**Dedup-Verhalten:**
Die Registry hat `StructuredConfigBuilder` für 4 Extensions mit gleicher Instance. `filter_skeleton` / `_build_symbol_index` deduplizieren via `id(builder)`.

**Beispiele:**

Python:
```python
# input: mod.py
def calculate_total(items): ...  # L2


class ShoppingCart:  # L5
    def __init__(self): ...
    def add_item(self, x): ...


CART_MAX_SIZE = 100  # L11

# output:
[
    SkeletonEntry("calculate_total", "function", "mod.py", 2, 3),
    SkeletonEntry("ShoppingCart", "class", "mod.py", 5, 9),
    SkeletonEntry("add_item", "function", "mod.py", 8, 9),
    SkeletonEntry("CART_MAX_SIZE", "variable", "mod.py", 11, 11),
]
```

TypeScript:
```typescript
// input: mod.ts
export class User {
  greet(): string { ... }   // L3
}
```
```
→ SkeletonEntry("User", "class", "mod.ts", 1, 4)
→ SkeletonEntry("User.greet", "method", "mod.ts", 3, 3)  (qualifiziert!)
```

JSON:
```json
// input: agent.json
{"log_level": "INFO", "mode": "standard"}
```
```
→ SkeletonEntry("log_level", "key", "agent.json", 1, 1)
→ SkeletonEntry("mode", "key", "agent.json", 1, 1)
```

**Wer nutzt das?** K6 (Symbol-Index für Expansion), K8 (filter_skeleton).

**Voraussetzungen pro Builder:**
- Python AST: stdlib (immer OK)
- Tree-sitter: optional `pip install tree_sitter tree_sitter_typescript`
- Go: stdlib Regex
- Config: stdlib `json`, optional `pyyaml`

---

## K8 — `filter_skeleton()`

**Datei:** `samuel/slices/implementation/context_builder.py`

**Zweck:** Findet Skeleton-Symbole die im Issue-Text vorkommen (umgekehrtes Matching, v1-Style). Liefert Kontext-Sektion "Repo-Skeleton" mit Zeilennummern.

**Algorithmus:**
1. Extrahiere Backticks aus Issue-Text: `` `symbol_name` `` → Set
2. Extrahiere alle Identifier aus Issue-Text: Regex `[A-Za-z_][A-Za-z0-9_]{3,}` → Set
3. Scan Projekt mit allen Buildern (deduped via `id()`):
   - Für jeden Eintrag: prüfe ob `entry.name` in Backticks (Score +5) oder all_tokens (Score +3)
   - Plan-File-Bonus: +4 wenn Datei in `plan_files`
   - Magic-Name-Filter: `__init__`, `__main__`, etc. werden gefiltert (außer Backtick oder Plan-File)
4. Sortiere nach Score
5. Max 60 Matches (`max_entries`)

**Score-Tabelle:**
| Match-Typ | Score |
|---|---|
| Symbol in Backticks | +5 |
| Symbol als Token im Issue | +3 |
| Datei ist Plan-File | +4 |
| (kumulativ, max 12) | |

**Beispiel:**
```
Issue: "Füge `__version__` in `samuel/cli.py` ein."

Skeleton-Scan findet:
  __version__ in samuel/__init__.py    → Backtick (+5), ist plan_file (+4) = 9
  _cmd_run in samuel/cli.py            → Token (+3), ist plan_file (+4) = 7
  bootstrap in samuel/core/bootstrap.py→ Token (+3) = 3

Ergebnis sortiert: __version__ (9), _cmd_run (7), bootstrap (3)
```

**Sprachen:** Sprachagnostisch — aggregiert Outputs aller registrierten Builder.

**Output:** `list[tuple[str, SkeletonEntry]]` — Pairs von (rel_path, entry)

**Rendering (`render_skeleton_section`):**
```markdown
## Repo-Skeleton (keyword-gefiltert, mit Zeilennummern)

### samuel/__init__.py
- **variable** `__version__` Zeilen 1-1

### samuel/cli.py
- **function** `_cmd_run` Zeilen 84-100
```

**Geht an:** K10 (Region-Anker), K11 (Prompt-Sektion).

---

## K9 — `grep_keywords()`

**Datei:** `samuel/slices/implementation/context_builder.py`

**Zweck:** Findet Code-Zeilen die Keywords aus K3 enthalten. Liefert zusätzliche Orientierung für den LLM, ergänzt das Skeleton.

**Algorithmus:**
1. Kompiliere Regex `\b{keyword}\b` (Word-Boundary, case-insensitive) pro Keyword
2. Scan Projekt via `iter_project_files` mit `CODE_EXTENSIONS`
3. Respektiert Arch-Scope (`allowed` / `blocked`) — wichtig!
4. Max 5 Hits pro Keyword (`max_hits_per_keyword`)
5. Top-5 Keywords aus K3 (`keywords[:5]`)

**Word-Boundary:** Das Muster ist `re.compile(rf"\b{kw}\b", re.IGNORECASE)`
(`context_builder.py:448`). Ohne `\b` würde "cli" auch "click" treffen —
früher eine massive Rauschquelle bei HTML-Klassennamen.

**Scope-Filter:** `grep_keywords()` nimmt `allowed_scopes` und `blocked_scopes`
entgegen (aus K5) und überspringt Dateien in den blockierten Scopes.

**Beispiel:**
```
Keywords: ["health", "status", "dashboard"]
Arch-allowed: {samuel/server.py, samuel/slices/dashboard/, tests/test_server_dashboard.py}

Grep findet:
  samuel/server.py:46 — .health-row{display:flex;...}
  samuel/server.py:107 — <div class="card"><h3>Health</h3>...
  samuel/server.py:93 — <button class="tab" onclick="showTab('status')">
  samuel/slices/dashboard/handler.py:40 — def get_status(self):
  ...
```

**Rendering (`render_grep_section`):**
```markdown
## Keyword-Vorkommen im Projekt (Grep)

### `health`
- samuel/server.py:46 — `.health-row{display:flex;...}`
- samuel/server.py:107 — `<div class="card"><h3>Health</h3>...`

### `status`
- ...
```

**Sprachen:** Alle via `CODE_EXTENSIONS` (keyword-suche, keine Sprach-Parser).

**Geht an:** K10 (Region-Anker für Files ohne Skeleton-Match), K11 (Prompt-Sektion).

---

## K10 — `render_files_section()`

**Datei:** `samuel/slices/implementation/context_builder.py`

**Zweck:** Lädt Datei-Inhalte in den Prompt — aber **smart**: nur relevante Regionen, nicht komplette Files.

**Entscheidungs-Baum pro File:**

```
Datei exists?
├─ Nein → skip
└─ Ja
   ├─ total ≤ 150 Zeilen (SMALL_FILE_THRESHOLD_LINES)
   │  └─ komplett laden (mit Zeilennummern)
   ├─ Skeleton-Matches für diese Datei (aus K8) ?
   │  └─ Ja: Regions aus Matches ± 10 Zeilen (REGION_CONTEXT_LINES), merged
   ├─ Grep-Hits für diese Datei (aus K9) ?
   │  └─ Ja: Hit-Lines ± 10 Zeilen als Regions
   └─ total > 300 Zeilen (FALLBACK_TOC_THRESHOLD)
      ├─ Ja: nur Hinweis "Datei zu groß, kein Anker — Skeleton siehe oben"
      └─ Nein: erste `max_lines` (600) Zeilen (Fallback)
```

**Rendering mit Zeilennummern:**
```markdown
## Relevante Dateien (aus Plan)

### samuel/server.py (648 Zeilen)

_(Zeilen 3-34 von 648)_
​```
    3 | import json
    4 | import logging
    ...
​```

_(Zeilen 83-120 von 648)_
​```
   83 | <div class="tab-content" id="tab-status">
   ...
​```
```

**Merge-Regel:** Überlappende oder benachbarte Regionen werden zu einem Block zusammengefasst (`_merge_ranges`).

**Konstanten:**
| Name | Wert | Bedeutung |
|---|---|---|
| `SMALL_FILE_THRESHOLD_LINES` | 150 | darunter: immer komplett |
| `REGION_CONTEXT_LINES` | 10 | ± um Match-Region |
| `FALLBACK_TOC_THRESHOLD` | 300 | darüber: kein Blind-Load |
| `MAX_RELEVANT_FILE_LINES` | 600 | max Fallback-Fenster |

**Beispiel (server.py 648 Zeilen für Dashboard-Issue):**
- Skeleton-Match: 0 (keine Symbolnamen im Issue)
- Grep-Hits: 5+ (`health`, `status`, `dashboard`)
- → 6 Regions mit insg. ~200 Zeilen (statt 648)

**Sprachen:** Sprachagnostisch — Text wird zeilenbasiert gerendert.

**Geht an:** K11 (Sektion `relevant_files`).

---

## K11 — `build_full_context()`

**Datei:** `samuel/slices/implementation/context_builder.py`

**Zweck:** Orchestriert K3–K10, aggregiert alle Kontext-Sektionen in ein Dict.

**Signatur:**
```python
build_full_context(
    *,
    issue_number: int,
    issue_title: str,
    issue_body: str,
    plan_text: str,
    project_root: Path,
    skeleton_builders: list[ISkeletonBuilder] | None = None,
    architecture_constraints: list[str] | None = None,
    architecture_config_path: Path | None = None,
    exclude_dirs: set[str] | None = None,
    keyword_extensions: set[str] | None = None,
) -> dict[str, str]
```

**Ablauf:**
```
1. keywords       = extract_keywords()              [K3]
2. plan_files     = extract_plan_files()            [K4]
3. arch_data      = load(config/architecture.json)  [K5]
4. arch_scope     = _resolve_expansion_scope(plan_files, modules, policy)
5. module_info    = _resolve_module_info(plan_files, modules)
6. plan_files     = expand_via_symbol_references(..., allowed/blocked)  [K6]
7. skeleton_match = filter_skeleton(..., plan_files, issue_text)        [K8]
8. grep_hits      = grep_keywords(keywords[:5], allowed/blocked)        [K9]
9. relevant_files = render_files_section(plan_files, skel, grep)        [K10]

return {
  "keywords":       "comma-separated",
  "plan_files":     "- `file.py`",
  "skeleton":       "## Repo-Skeleton (keyword-gefiltert, ...)",
  "grep":           "## Keyword-Vorkommen ...",
  "relevant_files": "## Relevante Dateien (aus Plan) ...",
  "module_context": "## Betroffene Module ...",
  "constraints":    "## Architektur-Constraints ...",
}
```

**Output:** Dict mit 7 Markdown-Sektionen (jede optional leer).

**Geht an:** K12 (Prompt-Assembly).

---

## K12 — `_build_implement_prompt()`

**Datei:** `samuel/slices/implementation/handler.py`

**Zweck:** Setzt aus Issue-Daten + Context-Dict den finalen LLM-Prompt zusammen.

**Struktur (Reihenfolge):**
```
1. PROMPT_GUARD_MARKERS  (Unveränderliche Schranken, Ignoriere Anweisungen)
2. # Implementierung für Issue #N
3. ## Issue-Titel  (in <user-content>-Tags, XSS-safe)
4. ## Issue-Beschreibung
5. ## Plan  (wenn vorhanden)
6. ## Suchbegriffe aus Issue/Plan
7. ## Plan-referenzierte Dateien
8. ## Betroffene Module (Architektur-Rolle)   ← K11 module_context
9. ## Repo-Skeleton                            ← K8
10. ## Keyword-Vorkommen (Grep)                ← K9
11. ## Relevante Dateien (aus Plan)            ← K10
12. ## Architektur-Constraints                 ← K5
13. ## Aufgabe  (Patch-Format-Anleitung)
    - REPLACE LINES Format
    - SEARCH/REPLACE Format
    - WRITE Format (neue Dateien)
```

**Sicherheits-Wrapper:**
- Issue-Content wird in `<user-content>...</user-content>` eingeschlossen
- zentral definierte Guards am Prompt-Anfang (weiche Prompt-Layer-Maßnahme)
- jeder Implementierungsrunden-Prompt wird über denselben advisory
  `IPromptRiskAnalyzer` bewertet; Treffer erzeugen begrenzte Evidence, aber
  keine technische Injection-Schranke

**Output:** `str` — der komplette LLM-Prompt.

**Geht an:** K13 (Validator), K14 (LLM-Call).

---

## K13 — `validate_context()`

**Datei:** `samuel/slices/implementation/context_validator.py`

**Zweck:** Pre-LLM Gate. Blockt den LLM-Call bei offensichtlich unzureichendem Kontext. Spart Tokens.

**Signatur:**
```python
validate_context(
    *, issue_title, issue_body, plan_text, context, prompt,
) -> ContextValidation
```

**Checks:**

| Check | Resultat | Schwelle |
|---|---|---|
| Issue-Title leer | BLOCK | - |
| Issue-Body < 20 chars | BLOCK | - |
| Kein Skeleton AND kein Plan-File AND kein Relevant-File AND kein Grep | BLOCK | - |
| Kein Plan-File AND kein Relevant-File | WARN | - |
| Kein Plan-Text | WARN | - |
| Prompt < 200 Tokens | BLOCK | `MIN_PROMPT_TOKENS` |
| Prompt > 80_000 Tokens | BLOCK | `MAX_PROMPT_TOKENS` |
| Prompt > 30_000 Tokens | WARN | `WARN_PROMPT_TOKENS` |

**Output (`ContextValidation`):**
```python
@dataclass
class ContextValidation:
    ok: bool
    issues: list[str]  # Blocker
    warnings: list[str]  # Advisories
    prompt_tokens_est: int
    breakdown: dict[str, int]  # chars pro Sektion
```

**Bypass:** Im Handler per `enforce_context_quality=False` (Tests).

**Beispiel — OK:**
```
prompt_tokens_est: 7706
issues: []
warnings: []
breakdown: {skeleton: 775, relevant_files: 25262, ...}
→ ok=True → LLM-Call startet
```

**Beispiel — BLOCK:**
```
issues: [
  "Issue body too short (3 chars)",
  "No code context found at all",
  "Prompt too small (174 tokens)"
]
→ ok=False → WorkflowBlocked-Event, kein LLM-Call
```

**Geht an:** K14 (wenn OK) oder `WorkflowBlocked`-Event (wenn BLOCK).

---

## K14 — `run_llm_loop()`

**Datei:** `samuel/slices/implementation/llm_loop.py`

**Zweck:** Iterativer LLM-Call mit Patch-Anwendung und Retry-mit-echtem-Code bei Fehlern.

Der `ImplementationHandler` bindet vor Eintritt in den Loop Issue und
Command-`correlation_id` sowie die beim exakten Plan-Approval wiedergefundene
Workflow-Budgetzulassung im gemeinsamen Core-Kontext. Der Metering-Adapter
publiziert deshalb jedes `LLMCallCompleted` dieses Loops unter demselben
Workflow-Run und setzt `workflow_correlation_bound=true`. Die Bindung wird
nicht als freies `kwargs` an den zugrunde liegenden Provider weitergereicht;
außerhalb eines solchen Scopes bleibt ein Call ausdrücklich ungebunden (#675).
Der Workflow-Budgetadapter reserviert vor jeder physischen Provideranfrage des
Loops, einschließlich Retry und Fallback, den konservativen Eingabe-Bound und
den erzwungenen Ausgabe-Bound. Fehlende Zulassung oder Deckung blockiert vor
Sendung. Unbekannte Usage hält die volle Reservation über Neustart und Resume.

**Schleife:**
```
MAX_ROUNDS = 5
MAX_SLICE_ROUNDS = 3

transaction = WorkspaceTransaction()  # erster Zugriff je Zielpfad erfasst Vorzustand
git_control_paths = git_control_plane_paths(project_root)  # read-only, einmal je Loop

for round in 1..5:
    response = llm.complete([...], **llm_kwargs)   # task="implementation"

    if is_truncated_stop_reason(response.stop_reason):
        result = {"reason": "token_limit", "success": False}
        break

    patches = parse_patches_structured(response.structured)
    if not patches:
        patches = parse_patches(response.text)
    if not patches:
        # #152: Nur jetzt gezielte SLICE-Anforderungen aufloesen.
        slice_requests = parse_slice_requests(response.text)
        if slice_requests and slice_rounds_used < MAX_SLICE_ROUNDS:
            current_prompt += aufgeloeste Slices;  slice_rounds_used += 1
            continue                            # zaehlt als Runde, kein Patch-Versuch
        terminal_reason = "no_parseable_patches"
        terminal_diagnostic = {"round": round, "patch_count": 0,
                               "applied_patch_count": len(patches_applied)}
        break

    resolved_patches = resolve_all_patch_targets(project_root, patches)
    if any target is rejected:
        result = {"reason": "unsafe_patch_target", "success": False,
                  "diagnostic": content_free_reason_codes_and_counts}
        break                                      # kein Patch der Antwort angewendet

    for patch, canonical_file_path in resolved_patches:
        apply(patch) → (ok, msg)                # ggf. mit Attribution-Marker (#270)
        if ok: patches_applied += patch
        else:  round_failures += (msg, patch)

    if no round_failures:
        break

    # #319: Hard-Stop gegen Endlosschleifen
    if round_applied_count == 0: consecutive_zero_progress += 1
    else:                        consecutive_zero_progress = 0
    if consecutive_zero_progress >= 2 and round_num >= 2:
        result = {"reason": "no_progress", "success": False,
                  "diagnostic": bounded_redacted_apply_failures}
        break

    current_prompt = build_retry_prompt(
        base_prompt, round_num, failures_with_patches, project_root,
    )
    # Retry lädt echten Quellcode der gescheiterten Files!

if result.success:
    transaction.commit()                         # alle Loop-Patches behalten
else:
    result.rollback = transaction.rollback()     # alle berührten Pfade restaurieren
    if result.rollback.status == "completed":
        result.patches_rolled_back = len(patches_applied)
        result.patches_applied = []
    elif result.rollback.status == "not_needed":
        result.patches_rolled_back = 0
        result.patches_applied = []
    else:
        result.trigger_reason = result.reason
        result.reason = "workspace_rollback_failed"

if result.trigger_reason == "token_limit" or result.reason == "token_limit":
    on_token_limit(..., result.rollback)          # erst nach dem Restore
```

**Neun Erweiterungen, die frühere Fassungen nicht kannten:**

| # | Was | Wirkung |
|---|---|---|
| #152 | **Slice-Request-Loop.** `slice_resolver(rel, start, end)` löst `SLICE: datei:10-40`-Anforderungen des LLM auf | Das Modell kann gezielt Code nachfordern, statt zu raten. Gedeckelt auf `MAX_SLICE_ROUNDS = 3` und gegen Re-Scan dedupliziert, damit daraus kein sequentielles Durchblättern der Codebasis wird |
| #270 | **Attribution.** Ist das Feature-Flag `llm_attribution` aktiv, wird jeder Patch vor dem Apply mit einem Inline-Marker versehen | Schlägt der markierte Apply fehl (z.B. an der `.py`-AST-Validierung), fällt die Schleife auf den **unmarkierten** Patch zurück — die Kennzeichnung darf nie einen sonst gültigen Patch verwerfen |
| #319 | **Zero-Progress-Abbruch.** Zwei aufeinanderfolgende Runden ohne einen einzigen angewendeten Patch beenden den Lauf mit `reason="no_progress"` | Vorher musste der Operator solche Läufe von Hand abbrechen. Greift frühestens ab Runde 2 |
| #588 | **No-Patch-Terminal.** Eine nicht truncierte Antwort ohne strukturiert oder textuell parsbaren Patch endet mit `reason="no_parseable_patches"` | Runde und Patchanzahl werden inhaltsfrei diagnostiziert; Antworttext und Secrets werden nicht in Resultat oder `WorkflowBlocked` kopiert |
| #598 | **Atomarer Loop-Arbeitsbaum.** Der Vorzustand jedes erstmals berührten Pfads wird vor dem Apply in-memory erfasst | Erfolg übernimmt alle Patches; Tokenlimit, No-Patch, No-Progress, Partial-Failure und Exceptions restaurieren Inhalt, Existenz und Modus ohne Git-Reset. Restore-Fehler werden `workspace_rollback_failed` |
| #600 | **Projektwurzel-gebundene Patchziele.** Alle strukturierten oder textuellen Ziele einer Antwort werden vor dem ersten Apply kanonisch validiert | Nur normalisierte relative POSIX-Pfade innerhalb des aufgelösten `project_root`; absolute, traversierende und per Symlink externe Ziele blockieren als `unsafe_patch_target` mit inhaltsfreien Codes |
| #603 | **Lokale Git-Control-Plane.** `.git` ist in jeder Pfadtiefe reserviert; Git-, Common-, Index- und Object-Pfade werden einmal pro Loop mit einem read-only Core-Git-Aufruf effektiv aufgelöst | Directory-/File-Marker, Submodule/Worktree, separate/linked Git-Dirs und wirksame `GIT_*`-Overrides blockieren vor Excerpt-Read, Snapshot und Write mit `patch_target_rejected:git_control_plane`; normale Dotfiles bleiben erlaubt |
| #601 | **Mutationsfreie fachliche Patchablehnung.** Line-Patches berechnen SEARCH/REPLACE- und REPLACE-LINES-Kandidaten ohne Write; JSON validiert den vollständigen Kandidaten vor dem Schreiben | Ungültiges JSON, fehlender SEARCH, ungültige Range und vorhandene fachliche Validatorfehler melden `False`, ohne Inhalt oder relevante Metadaten zu verändern. Der Retry sieht den letzten gültigen Stand; I/O-Fehler während des Writes bleiben Loop-Transaktionsscope |
| #606 | **Python-WRITE vor Write per AST.** Der vollständige normalisierte Inhalt verwendet denselben `LinePatchApplier.validate()`-Hook vor `mkdir`/Write wie partielle Python-Patches | Ungültige Text-/Structured-WRITEs melden `False`, erstellen kein Neuziel und verändern bestehende Bytes/Metadaten nicht. Ein verifiziert unveränderter Vorsorge-Snapshot wird freigegeben, damit terminaler Rollback keine MTime umschreibt; Gate 9 bleibt commitgebunden |
| #828 | **Terminale Apply-Diagnose.** Fachliche Applier-Ablehnungen werden nach sicherer Zielauflösung klassifiziert und begrenzt redigiert | `no_progress` und `partial_failure` führen Fehlercode, kanonisches relatives Ziel und höchstens 500 Zeichen Detail bis in `WorkflowBlocked`; Providerantwort und unredigierte Meldung bleiben außerhalb der Terminal-Evidence. Der kompatible Blockgrund `self_mode_no_progress` bezeichnet dabei keinen tatsächlichen Agentmodus |

**Retry-Prompt:**
```
[Original-Prompt]

## Patch-Fehler in Runde N — KORRIGIEREN
- SEARCH not found in cli.py
- line range 50-60 out of bounds ...

## Aktueller Quellcode der betroffenen Dateien
### cli.py (aktueller Zustand)
​```
   42 | def _build_parser():
   43 |     p = argparse.ArgumentParser(...)
   ...
​```
```

**Code-Anker bei Fehler:**
- `replace_lines` Patch: ± 10 Zeilen um die Zielrange
- `search_replace` Patch: finde erste Zeile im File, ± 10 Zeilen
- unbekannt: erste 200 Zeilen

**Output:**
```python
{
    "success": bool,  # keine Failures UND mindestens ein Patch angewendet
    "reason": "complete"
    | "partial_failure"
    | "token_limit"
    | "no_progress"
    | "no_parseable_patches"
    | "unsafe_patch_target"
    | "workspace_rollback_failed",
    "round": int,
    "patches_applied": list[dict],
    "failures": list[str],
    "input_tokens": int,
    "output_tokens": int,
    "rounds_stats": list[dict],  # #319: pro Runde applied/failed
    "model": str,  # zuletzt tatsaechlich genutztes Modell
    "rollback": {  # bei erfolglosem Loop, ausschließlich inhaltsfreie Zahlen
        "status": "completed" | "not_needed" | "failed",
        "files_restored": int,
        "files_removed": int,
        "directories_removed": int,
        "failures": int,
    },
    "patches_rolled_back": int,
    "trigger_reason": str,  # nur bei workspace_rollback_failed
    "diagnostic": {  # no_parseable, unsafe target oder Apply-Ablehnung
        "kind": "apply_failure",  # nur bei Apply-Ablehnung
        "round": int,
        "patch_count": int,
        "applied_patch_count": int,  # no_parseable oder Apply-Ablehnung
        "rejected_patch_count": int,  # nur unsafe_patch_target
        "rejection_codes": list[str],  # nur unsafe; nie Rohpfade
        "apply_failures": [  # nur Apply-Ablehnung; max. 10 Einträge
            {"code": str, "target": str, "detail": str},
        ],
    },
}
```

`success` verlangt **beides**: keine offenen Failures *und* mindestens einen
angewendeten Patch. Eine nicht truncierte Runde, in der das LLM gar nichts
Parsebares liefert, gilt nicht als Erfolg und endet eindeutig als
`no_parseable_patches`, niemals als `complete`. Der Handler publiziert dazu
`WorkflowBlocked(task="implementation")` mit derselben Reason, einer
nichtleeren Fehlerkennung und der inhaltsfreien Diagnose. Modell- und
Stop-Metadaten bleiben in ihren vorhandenen Auditpfaden; der Antwortinhalt wird
nicht in diese Terminaldiagnose übernommen.

Fachlich abgelehnte, sicher aufgelöste Patches erhalten zusätzlich eine
konkrete Apply-Diagnose. Sie klassifiziert unter anderem fehlenden SEARCH,
ungültige Zeilenbereiche, Validator-/JSON-Fehler und fehlende Ziele; unbekannte
Appliergründe bleiben als `apply_rejected` sichtbar. Ziel und Detail werden
secret-bereinigt und begrenzt. Der frühe `no_progress`-Pfad publiziert diese
Diagnose mit derselben Korrelation im `WorkflowBlocked`; sein historischer
Reason-Code `self_mode_no_progress` bleibt unabhängig vom tatsächlichen
Agentmodus bestehen (#828).

Bei jedem erfolglosen Rückgabepfad ergänzt der Wrapper eine inhaltsfreie
`rollback`-Evidence. Nach vollständiger Wiederherstellung ist
`patches_applied=[]`; `patches_rolled_back` hält die Zahl der zuvor
als erfolgreich angewendet gezählten Patches fest. Ein Restore-Fehler erhält
den ursprünglichen Grund in `trigger_reason`, blockiert aber terminal als
`workspace_rollback_failed`. `TokenLimitHit` wird erst nach dem Restore
publiziert und enthält nur Rollback-Status und Dateianzahlen.

Ein `ProviderUnavailable` aus dem Implementation-Loop wird nach dessen
Workspace-Rollback im bestehenden Handler als korreliertes
`WorkflowBlocked(reason=provider_unavailable)` behandelt. Die begrenzte
`provider_error`-Evidence enthält nur `code`, `retryable` und einen optionalen
HTTP-`status`; Providertext und Responsepayload werden nicht übernommen. Das
gilt ebenso, wenn ein gebundener `HealingSuggested` die Implementation erneut
anstößt. Der Healing-Claim ist zu diesem Zeitpunkt bereits als `attempted` mit
Outcome abgeschlossen.

Die Garantie endet an der prozesslokalen K14-Grenze: ein harter
Prozess-/Hostabbruch (#482), K16 und das kumulative Tokenbudget (#549) sind
nicht durch die Loop-Transaktion abgedeckt. Schema v10 persistiert
Round-Checkpoints weiterhin nur diagnostisch mit `resume_eligible=false`.
ADR-0482 Stufe 4 (#633) setzt davon getrennt ausschließlich die nach dem
erfolgreichen Loop erzeugten sicheren K16-Finalisierungsgrenzen fort; ein
halber LLM-/Patch-Round, Prompt- oder Tokenzustand wird nie rekonstruiert.
Stufe 5a (#666) ergänzt den unterstützten State-Restore als neue
Autoritätslinie. Bis ihr vollständiger Operator-Reconcile abgeschlossen ist,
darf auch ein formal resumefähiger K16-Checkpoint keine Wirkung entfalten.
Stufe 5b (#667) ergänzt daran Katalog, Dry-Run, Managed Backups und
Score-Replay; sie macht einen K14-Round-Checkpoint ausdrücklich nicht
fortsetzbar. Das deaktiviert ausgelieferte 5c-Fundament (#673) fügt nur
operatorgeführte Kategorie-Autorität und eine allowlist-basierte
`score_derivations`-Strategie hinzu; es verändert K14 und Resume nicht.
Fachlich abgelehnte Applier-Patches bleiben vor dem Write
mutationsfrei (#601); absolute, traversierende, per Symlink externe und
effektive lokale Git-Control-Plane-Patchziele blockiert die vorgeschaltete
Zielprüfung (#600, #603). `rounds_stats` landet im
Self-Mode zusammen mit Grund, Tokens und angewendeter Patchanzahl in
`data/logs/self_mode_metrics.jsonl`; das zuletzt verwendete `model` steht im
Loop-Resultat, wird in diesem Health-Record derzeit aber nicht persistiert.

**Sprachen:** Sprachagnostisch — Patch-Parser + Retry sind Format-basiert, nicht Sprach-basiert.

**Geht an:** K15 (Patches zum Anwenden) — Anwendung passiert eigentlich inline in K14, K15 ist nur der Applier.

---

## K15 — `patch_parser` + Applier

**Datei:** `samuel/slices/implementation/patch_parser.py`

**Zweck:** Parst LLM-Response zu Patches und wendet sie auf das Filesystem an.

Vor der Applier-Auswahl löst
`samuel/slices/implementation/patch_targets.py` jedes Patchziel kanonisch
gegen `project_root` auf. K14 validiert die komplette Antwort vor dem ersten
Apply und ersetzt das unvertrauenswürdige Ziel durch den kanonischen relativen
Pfad. Damit verwenden Applier, Transaktion, Resultat und Git-Staging dieselbe
gebundene Adresse. Ablehnungen werden nicht an den Retry-Codeauszug übergeben
und spiegeln den Rohpfad weder im Resultat noch im Event. Zuvor liefert
`samuel.core.git.git_control_plane_paths()` über einen einzigen read-only
`rev-parse`-Aufruf `.git` sowie die effektiven absoluten Git-/Common-/Index-/
Object-Pfade. Ein Ziel auf oder unter diesen Pfaden verwendet die inhaltsfreie
Ablehnung `git_control_plane`; schlägt die Discovery außerhalb eines
Git-Worktrees fehl, bleibt `.git` dennoch reserviert.

**Unterstützte Formate (drei):**

### REPLACE LINES (bevorzugt, v1-Style)
```
## datei.py
REPLACE LINES 10-25
[neuer Code]
END REPLACE
```

### SEARCH/REPLACE
```
## datei.py
<<<<<<< SEARCH
[alter Code exakt]
=======
[neuer Code]
>>>>>>> REPLACE
```

### WRITE (neue Datei)
```
## WRITE: neue_datei.py
[kompletter Inhalt]
## END_WRITE
```

### Zwei weitere Parser im selben Modul

Neben `parse_patches()` (die drei Textformate oben) gibt es:

- **`parse_patches_structured(data)`** (#335) — Patches aus **validiertem JSON**
  statt aus SEARCH/REPLACE-Freitext. Der Freitext-Parser bleibt der Weg für
  Modelle ohne verlässliches Structured-Output; wo strukturierte Antworten
  möglich sind, entfällt das Parsen von Trennzeilen.
- **`parse_slice_requests(text)`** (#152) — erkennt `SLICE: pfad:start-end`
  im LLM-Output. Das sind **keine Patches**, sondern Nachforderungen von
  Code-Ausschnitten; sie werden in K14 vor dem Patch-Versuch ausgewertet.

**Applier-Registry** (`PATCH_APPLIERS`, Auswahl über die Dateiendung):

| Endung | Applier | Besonderheit |
|---|---|---|
| `.py` | `LinePatchApplier` | alle drei Operationen einschließlich WRITE vor Verzeichnisanlage/Write per `ast.parse()` (#606) |
| `.json` | `JSONPatchApplier` | Kandidat schreibfrei berechnet und vor Write per `json.loads()` validiert (#601) |
| `.yaml` / `.yml` | `YAMLPatchApplier` | delegiert unverändert an `LinePatchApplier` — **keine** YAML-Validierung |
| alles andere (`*`) | `LinePatchApplier` | reine Zeilenoperation, keine Syntaxprüfung |

`get_applier()` fällt für unbekannte Endungen auf den `*`-Eintrag zurück.

> `YAMLPatchApplier` ist ein Passthrough ohne eigene Prüfung. Ein
> YAML-Syntaxfehler wird also erst später auffällig — anders als bei `.py`
> und `.json`.

**Output:** `list[tuple[bool, str]]` — (applied, message)

Ein fachliches `False` bedeutet für die vorhandenen Applier-Pfade keine
Mutation: Kandidat und Validierung liegen vor dem sichtbaren Write. Dies gilt
nicht als allgemeine atomare Filesystem-Zusage; ein I/O-Fehler während eines
bereits begonnenen Writes propagiert als Exception und wird erst von der
prozesslokalen Workspace-Transaktion behandelt. Nach einer fachlichen
Ablehnung gibt der Loop den vorsorglichen Snapshot nur frei, wenn Existenz,
Bytes und Modus unverändert sind; dadurch bleibt auch die MTime ohne unnötigen
Rollback-Write stabil (#606).

**Sprachen:** Sprachagnostisch. Python-spezifisch: syntax-validation nach Patch.

**Geht an:** K16 (bei success → git commit), sonst Retry (K14).

---

## K16 — Git-Operationen + `CodeGenerated`-Event

**Dateien:**
- `samuel/core/git.py` — Git-Adapter (stdlib subprocess)
- `samuel/core/ports.py` — `IWorkspaceManager`
- `samuel/adapters/workspace/git.py` — gemeinsamer Worktree-Adapter
- `samuel/slices/implementation/handler.py` — orchestriert

**Zweck:** Bindet den Candidate an einen separaten Run-Worktree, sichert ihn
inhaltsgebunden in einem Git-Branch und publiziert `CodeGenerated`.

Der Run-Worktree wird tatsächlich schon **vor K2/K11/K14** erzeugt. Dadurch
lesen Kontext, Slice-Resolver und Patch-Loop denselben Branch-/Run-gebundenen
Baum, den K16 finalisiert; der Hauptcheckout wird nicht mutiert. Ein
Healing-Nachlauf startet am verifizierten Remote-Head desselben Branches.

**Ablauf (nur wenn `result["success"]`):**
```python
branch_name = f"samuel/issue-{issue_number}"
workspace = workspace_manager.acquire_run(
    repository_root=project_root,
    workspace_id=bound_repository_run_branch_key,
    branch=branch_name,
    base_ref="main",
    expected_head=resume_head_sha,
)
project = workspace.path

patched_files = sorted({patch["file"] for patch in patches if patch.get("file")})
_git.stage_files(patched_files, cwd=project)
parent = _git.head_sha(cwd=project)
tree = _git.index_tree(cwd=project)
authority.put_checkpoint(
    boundary="commit_pending",
    resume_eligible=True,
    workspace_id=workspace.workspace_id,
    expected_parent=parent,
    expected_tree=tree,
    contract_policy_schema_binding=resume_binding,
)
authority.put_intent(
    operation="commit",
    workspace_id=workspace.workspace_id,
    expected_parent=parent,
    expected_tree=tree,
)
trailers = commit_trailers(
    model=model,
    system_version=build_info.product_version,
    build_revision=build_info.revision or "",
    build_dirty=bool(build_info.dirty),
    external_visible=attribution_enabled,
)
commit_sha = _git.commit_tree_transaction(
    f"feat: Issue #{N} — LLM-generierte Implementierung\n\n"
    f"Patches: {len(patches)}\n"
    f"Rounds: {round}\n"
    f"{trailers}",
    expected_parent=parent,
    expected_tree=tree,
    cwd=project,
)
authority.finish_intent(operation="commit", parent=parent, tree=tree, head_sha=commit_sha)
authority.put_checkpoint(boundary="push_pending", head_sha=commit_sha)
authority.put_intent(operation="push", expected_head=commit_sha)
_git.push(branch_name, cwd=project)
assert scm.resolve_ref(branch_name) == commit_sha
authority.finish_intent(operation="push", remote_head=commit_sha)
authority.put_checkpoint(boundary="gates_pending", head_sha=commit_sha)

bus.publish(
    CodeGenerated(
        payload={
            "issue": issue_number,
            "patches_applied": len(patches),
            "rounds": round,
            "branch": branch_name,
            "workspace_id": workspace.workspace_id,
        }
    )
)
```

`commit_tree_transaction()` ruft keine geerbten Repository-Hooks auf. Es
prüft den Index-Tree vor und nach `commit-tree` und bewegt/erzeugt die Branch-
Ref mit `git update-ref -m ... --stdin` per CAS-/Create-Semantik. Required
Signing ohne konfigurierten Schlüssel blockiert. Während der synchronen
`CodeGenerated`-Kette kann Gate 11 zusätzlich einen detached
Verifikations-Worktree desselben Managers halten. Ein unerwarteter Abbruch
quarantänisiert den Run-Baum; normal terminale Bäume werden entfernt und ihre
Registryzeile bleibt bis zum kontrollierten `prune` diagnostizierbar.
Quarantänen tragen eine 168-Stunden-Operatorfrist, werden dadurch aber nicht
automatisch gelöscht. Nach dokumentierter Prüfung terminalisiert nur das
begründete CLI-Kommando `workspace discard` die Evidence.

Bei Prozessneustart konsumiert `ResumeCoordinator` über den Bus einen
`ResumePendingCommand`; er importiert weder Handler noch Adapter direkt. Vor
dem erneuten `ImplementCommand(resume_finalization=true)` erhält der vorhandene
Run-Worktree seinen OS-Lock. Der Implementation-Handler übernimmt danach nur
ein abgelaufenes Lease per CAS und vergleicht Repository, Issue/Korrelation,
Branch/Base, Workspace, Planning-Snapshot, Contract, Gate-Policy,
Gate-/Observation-Schema,
Signing-Policy, `git status --porcelain`, Index-Tree und HEAD. HEAD muss der
erwartete Parent oder der Parent-/Tree-identische Intent-Commit sein. Remote-
Drift, Dirty-/Index-/HEAD-Drift oder geänderte Policy quarantänisiert ohne
Reset/Force-Push. Nach bestätigtem Push publiziert derselbe Pfad
`CodeGenerated` erneut at-least-once; die nachfolgenden Wirkungen bleiben über
Subject und Intents idempotent.

**Ausgelöste Folge-Events (Workflow-Engine):**
- `CodeGenerated` → `CreatePR` Command → Subject-Bindung und vollständiger
  Gate-Lauf. Die statischen Gates 7b, 8, 9, 13a und 13b laufen vor der
  Candidate-Verifikation; ein Required-Preflight-Fehler überspringt Gate 11
  und alle weiteren internen/externen Gates explizit, ohne IMPORT/TEST zu
  starten. `PRCreated` entsteht nur bei bestätigter SCM-Antwort
  mit demselben Base-/Head-SHA. Fehlender Prüfgegenstand erzeugt
  `GateEvaluationUnavailable`, ein vollständiger Lauf genau ein
  `GateEvaluationCompleted`; die passive Evaluation erzeugt daraus
  `ScoreObserved` ohne Workflowkante. Ein Fehler der nachfolgenden
  PR-Erstellung erzeugt `PRCreationFailed`.
- PR-Gates laufen in `samuel/slices/pr_gates/handler.py`

**Voraussetzungen:**
- Git mit Worktree-/Plumbing-Unterstützung installiert, Repo initialisiert
- Push-Remote konfiguriert (`SCM_URL`, `SCM_TOKEN`, `SCM_REPO`)
- der konfigurierte `agent.default_branch` existiert und besitzt mindestens
  einen Commit
- `agent.workspace.work_dir` liegt auf lokalem Dateisystem außerhalb von
  Projektwurzel und `agent.data_dir`; Kapazitäts-/Quarantänegrenzen sind frei

---

## Anhang: Config-Dateien

Folgende Config-Dateien steuern die Pipeline (alle unter `config/`):

| Datei | Zweck | K-Nodes |
|---|---|---|
| `agent.json` | `default_branch`, `context.*`, `mode`, `workspace.work_dir`, Reserve-/Quarantänegrenzen, `git.signing_*` | K1–K2, K7, K11, K14–K16 |
| `architecture.json` | `modules` (Pfad→Rolle), `expansion_policy` (allowed/blocked scopes), `global_constraints` | K5, K11 |
| `features.json` | Allgemeine Funktionsschalter — für diese Pipeline vor allem `llm_attribution` (Inline-Marker in K14) und `architecture_context` | K14 |
| `llm.json` | Default-Provider + Fallback-Kette | K14 |
| `llm/defaults.json` | Per-Task-Parameter für `tasks.implementation` (`max_tokens`, `temperature`, `timeout`, `system_prompt: senior_python.md`) | K14 |
| `hooks.json` | Quality-Checks pro Dateiendung | K16 Folge |
| `gates.json` | PR-Gates | K16 Folge |
| `labels.json` | Workflow-Labels | K16 Folge |

### Beispiel `config/agent.json`:
```json
{
  "mode": "standard",
  "context": {
    "max_file_size_kb": 50,
    "exclude_dirs": ["__pycache__", ".git", ...],
    "keyword_extensions": [".py", ".js", ".ts", ...]
  }
}
```

### Beispiel `config/architecture.json`:
(siehe K5 oben — definiert Module + Rollen + expansion_policy)

---

## Pipeline-Lesetipps für verschiedene Personas

**Neue Entwickler:** Lies K1 → K11 → K12 → K14 in dieser Reihenfolge.

**Für Debugging eines schlechten Prompts:**
Starte bei K13 (Validator-Output), dann rückwärts über K11 zu K4/K3/K5.

**Für neue Sprach-Unterstützung:**
1. Implementiere neuen `ISkeletonBuilder` (K7)
2. Registriere in `samuel/adapters/skeleton/registry.py`
3. Test: K3 extrahiert Keywords (bereits sprachagnostisch), K6 findet Symbole, K10 rendert Files

**Für neue Projekt-Architektur:**
Passe `config/architecture.json` an (K5) — keine Code-Änderung nötig.

---

*Erstellt 2026-04-17. Zuletzt gegen den Code geprüft: 2026-09-01 auf
Ausgangscommit `53b859467bb28dced6e7208c020b70da4d708e75`.*
*Bei Pipeline-Änderungen dieses Dokument mitpflegen.*
