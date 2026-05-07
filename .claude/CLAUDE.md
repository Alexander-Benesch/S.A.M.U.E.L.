# CLAUDE.md — S.A.M.U.E.L. v2

## Projekt-Kontext

- **Arbeitsverzeichnis:** `/home/alexanderbenesch/S.A.M.U.E.L./` — das v2-Repo
- **NICHT anfassen:** `/home/alexanderbenesch/gitea-agent/` — v1, ARCHIVIERT (read-only auf Gitea). Nur als Referenz zum Lesen, keine Änderungen, keine Commits
- **Gitea-Repo:** `Alexmistrator/S.A.M.U.E.L` auf `http://192.168.1.60:3001`
- **Gitea-Token:** in `/home/alexanderbenesch/gitea-agent/.env` (GITEA_TOKEN)

## Dokumente (Priorität der Lektüre)

**Aktiv** (laufende Referenz):

1. **`docs/PHASE_WORKFLOW.md`** — 3-Stufen-Protokoll (Implementation → Phase-Review → QS-Check). Nur relevant wenn eine neue Phase aufgesetzt wird; Issue-getriebene Arbeit nutzt das nicht.
2. `docs/V2.1_GAP_ANALYSE_THEMATISCH.md` — kuratierte Gap-Analyse, Quelle für offene Backlog-Issues.
3. `docs/SAMUEL_ARCHITECTURE_V2.1.md` — Zielarchitektur (2856 Zeilen, 18 Kapitel). Bei Detail-Fragen konsultieren.
4. `docs/README_technical.md` + `docs/OPERATING_RULES.md` + `docs/PREMIUM_SETUP.md` — operative Doku.
5. **Aktueller Stand:** `docs/HANDOVER_<datum>.md` — letzte Übergabe-Doku, nennt Backlog + Aufmerksamkeitspunkte.

**Archiviert** (nur als historische Referenz, `docs/archive/`):

- `SAMUEL_V2_UMSETZUNGSPLAN.md` — Phasen 0a–13 alle abgeschlossen
- `V2_GAP_ANALYSE_KOMPLETT.md` — kuratierte Version `V2.1_THEMATISCH` ist aktiv
- `PHASE_1_HARDENING_CHARTER.md` — Phase 1 Hardening abgeschlossen
- `phases/PHASE_0b.md` — Phase 0b abgeschlossen
- `SELF_MODE_PROMPT_QUALITY_MEMO.md` — #259 closed
- `HANDOVER_2026-05-05.md` — vom Vortag, durch neuere Übergabe ersetzt

Die Architektur-Docs sind Referenz. Nicht raten — nachlesen.

## Arbeitsablauf pro Chat-Session

Phasen 0–13 sind alle abgeschlossen. Aktuell läuft die Arbeit **Issue-getrieben**: pro Backlog-Issue eigener Branch + PR.

### 1. Issue auswählen / anlegen
- Backlog auf Gitea: `Alexmistrator/S.A.M.U.E.L`
- Falls neues Thema: erst Issue mit klarer Spec + ACs anlegen, dann implementieren

### 2. Branch erstellen
```
git checkout main && git pull
git checkout -b feat/<NNN>-<slug>      # Neue Funktionalität
git checkout -b fix/<NNN>-<slug>       # Bugfix
git checkout -b refactor/<NNN>-<slug>  # Aufräumen
git checkout -b chore/<slug>           # Build/Repo-Hygiene
```

### 3. Implementieren
- Code + Tests + ggf. Doku
- Slice-Iso: kein Slice importiert direkt aus `samuel.adapters.*` (siehe `tests/test_architecture_v2.py`). Wenn nötig: Dependency-Injection im Wiring-Layer (`samuel/server.py`).
- WIP-Commits sind ok solange am Ende **ein** sauberer Commit gepusht wird (squash via `git reset --soft <main-sha>` + neuer commit).
- Author-Override pro commit: `git -c user.name=Alexmistrator -c user.email=axlvirtuell@gmail.com commit ...` (kein `git config`).

### 4. Tests + JS-Parse vor PR
```
.venv/bin/python -m pytest tests/ samuel/ -q
# Wenn server.py geändert: JS-Block parsen (memory: feedback_dashboard_js_escapes.md)
python3 -c "import samuel.server as s, re; m=re.search(r'<script>(.*?)</script>', s.DASHBOARD_HTML, re.DOTALL); open('/tmp/dash.js','w').write(m.group(1) if m else '')"
node --check /tmp/dash.js
```

### 5. PR + Merge
- PR via `gh`/`curl` auf Gitea-API anlegen
- Mergen, Branch lokal + remote löschen
- Issue automatisch via `Closes #<NNN>` im Commit-Body geschlossen

## v1-Code als Referenz

Beim Portieren von Logik aus v1:
- v1 liegt in `/home/alexanderbenesch/gitea-agent/`
- Logik verstehen, dann NEU schreiben für v2-Architektur
- NICHT kopieren und anpassen — die Architektur ist fundamental anders
- Imports: `from samuel.core.X import Y` — nie `from plugins` oder `from commands`

## Regeln

- Kein Code im Root — aller Python-Code unter `samuel/`
- Kein Slice importiert einen anderen Slice
- Slices importieren nur den Shared Kernel (`samuel.core.*`)
- Externe Systeme nur über Ports (`samuel.core.ports`)
- Tests leben beim Slice: `samuel/slices/planning/tests/test_handler.py`
- Übergreifende Tests (Architecture): `tests/test_architecture_v2.py`
