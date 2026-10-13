---
id: ADR-0618
title: Gemeinsamer Worktree-Manager mit Run- und Verifikationsprofil
status: accepted
decision_issue: 618
decision_date: 2026-08-29
decision_digest: sha256:58498383c26aad01d9ea4dab2d4acb9e0e557884260f09576a6ffdeaca3d785b
amendment: 2026-08-29 — Lifecycle-Diagramm ergänzt; 2026-09-01 — enge Git-Transport-Authentisierung nach #729 festgelegt
supersedes: []
superseded_by: []
---

# Gemeinsamer Worktree-Manager mit Run- und Verifikationsprofil

## Kontext

Implementation und Git-Finalisierung arbeiten heute im gemeinsamen
`project_root`. Die prozesslokale `WorkspaceTransaction` kann kontrollierte
Fehler zurückrollen, deckt aber keinen harten Prozessabbruch und keine
Konkurrenz eines zweiten Prozesses ab. Blockieren allein würde einen
kontaminierten Hauptcheckout für den nächsten Lauf zurücklassen.

Gate 11 besitzt bereits einen zweiten, temporären Mechanismus: Der
`ACVerificationHandler` erzeugt einen detached Worktree des exakten
Candidate-Heads. Ein zusätzlicher unabhängiger Run-Worktree-Mechanismus würde
Erzeugung, Git-Umgebung, Registry und Aufräumpfade duplizieren.

Ein Git-Worktree bindet einen Dateistand beziehungsweise Branch. Er isoliert
weder Prozessrechte noch Hostdateien, Netzwerk oder Ressourcen und ist deshalb
keine Sandbox.

## Entscheidung

S.A.M.U.E.L. erhält einen gemeinsamen Worktree-Manager mit zwei ausdrücklich
verschiedenen Profilen:

- Ein **Run-Worktree** ist an Run, Branch und gebundene Base gekoppelt,
  mutierbar und bleibt von Implementation über Healing bis zur Git-/PR-
  Finalisierung erhalten. Nicht automatisch auflösbare Zustände werden als
  eigener Baum quarantänisiert.
- Ein **Verifikations-Worktree** ist detached, ephemer, read-only beabsichtigt
  und an den exakten `head_sha` gebunden. Der vorhandene Gate-11-Pfad wird in
  dieses Profil migriert, nicht parallel weiterbetrieben.

Beide Profile verwenden dieselbe Registry, Erzeugung, gefährliche
`GIT_*`-Bereinigung, OS-Lock-Konvention, Speicherbuchung und Prune-Policy. Der
Run-Worktree ist die persistente Undo-/Quarantäneeinheit; ein zweites
persistentes Datei-Undo-Journal wird nicht eingeführt.

### Lifecycle

```text
Run:          booked -> active -> (reentrant healing) -> terminal -> prune
                              \-> unexpected stop -> quarantined -> operator review
Verification: booked -> active(detached head_sha) -> terminal -> prune

Ownership:    OS flock -> [später: DB lease] -> Zustandsprädikat
```

`prune` entfernt ausschließlich terminale Einträge. Eine fehlende aktive oder
quarantänisierte Verzeichnisressource wird nicht als Freigabe zum Löschen der
Git-Registry-Metadaten interpretiert.

## Control-Plane- und Inputgrenze

Worktrees liegen unter einem eigenen `work_dir`, getrennt von
`agent.data_dir`, State-Backups und Audit-Retention. Ein frischer Run-Worktree
übernimmt keine unversionierten `.env`, `data/`, `.venv`, Home- oder
Cachepfade des Hauptcheckouts. Jede erforderliche Toolchain-/Cache-Einbringung
braucht eine dokumentierte Allowlist und darf keine Secrets kopieren.

Gate-, Eval-, Architektur- und Security-Policy sowie Agentinterpreter und
Agentcode werden ausschließlich aus der vertrauenswürdigen Installation
aufgelöst. Der Agent importiert auch im Self-Mode keinen Pythoncode aus einem
Run-Worktree als eigene Control Plane.

Gefährliche Pfadvariablen (`GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`,
`GIT_OBJECT_DIRECTORY`, `GIT_COMMON_DIR` und
`GIT_ALTERNATE_OBJECT_DIRECTORIES`) werden fail-closed abgelehnt oder
bereinigt. Vom Manager gesetzte `GIT_AUTHOR_*`-/`GIT_COMMITTER_*`-Werte bilden
eine getrennte Identitäts-Allowlist. Push- und Signing-Credentials gelangen
nicht in die Workspace-Prozessumgebung.

### Git-Transport-Authentisierung (#729)

Alle Netzwerk-Git-Aufrufe aus `GitWorktreeManager` und `core/git.py` verwenden
denselben schmalen `IGitTransportAuth`-Port. Der mitgelieferte HTTP-
Referenzadapter bindet jede Delegation an genau die konfigurierte
SCM-Repository-URL und die konkrete Operation `fetch` oder `push`. Schema,
Host, Port und Repositorypfad müssen übereinstimmen; SSH-Remotes,
URL-Credentials, Query/Fragment und fremde Ziele blockieren geschlossen. Ohne
konfigurierte Transport-Authority ist nur ein ausdrücklich credentialfreier,
nichtinteraktiver Zugriff möglich; es gibt keinen versteckten Credential-
Fallback.

Die Referenzimplementierung verwendet ausschließlich den installierten,
absolut aufgelösten `samuel-git-askpass`-Helper. Benutzername und Token werden
nur im Environment des jeweiligen Netzwerk-Git-Kindprozesses bereitgestellt;
der Helper liest sie nicht aus seinen Argumenten. Verboten sind insbesondere
`git -c http.extraHeader=...`, Credentials in Remote-URLs und persistente
Credential-/Header-Einträge in `.git/config` oder globaler Git-Konfiguration.
Interaktive Prompts sowie System-/Global-Config und Credential-Helper sind für
diesen Aufruf deaktiviert. Lokale Git-, Candidate-, Gate- und Hook-Prozesse
erhalten die Askpass-Werte nicht.

Das beschreibt die Transportdelegation, nicht die Herkunft des Tokens: Der
bestehende `IAuthProvider` hält das Credential in der vertrauenswürdigen
S.A.M.U.E.L.-Runtime; beim ausgelieferten Env-Provider kann dort bereits
`SCM_TOKEN` existieren. Der Transportadapter erzeugt daraus keine zusätzliche
persistente Kopie und entfernt geerbte SCM-/Askpass-Werte aus allen lokalen
Git-Prozessen, kann aber die Credential-Sichtbarkeit der Runtime selbst nicht
aufheben.

Diese Argv-, URL-, Config- und Kindprozessgrenze verhindert keine Einsicht
durch andere Prozesse desselben Betriebssystembenutzers, wenn die Plattform
Runtime- oder Kindprozess-Daten wie `/proc/<pid>/environ` zugänglich macht. Das Referenzprofil ist deshalb
eine qualifizierte Single-User-/Service-Account-Grenze und keine vollständige
Mehrbenutzer-Credential-Isolation. Eine stärkere Benutzer-/Prozessgrenze
gehört zu einem externen Execution-/Runtime-Profil, nicht in einen eigenen
Secret-Store.

## Commit- und Recovery-Identität

Geerbte Repository-Hooks sind keine Recovery-Autorität. Eine kontrollierte
Commit-Transaktion bestimmt nach dem Staging mit `git write-tree` den
erwarteten Tree `T` und persistiert vor der Wirkung einen Intent aus
Workspace, Branch, Parent und `T`. `git commit-tree` erzeugt den Commit. Vor
dem Ref-Move muss der Index weiterhin exakt `T` ergeben; anschließend bewegt
oder erzeugt `git update-ref -m ... --stdin` die Branch-Ref per atomarer
CAS-/Create-Semantik.

Nach einem Abbruch gehört ein Commit nur dann zum Intent, wenn Parent und Tree
exakt übereinstimmen. Ein Commit-Trailer kann optionale menschliche Provenienz
liefern, ist aber keine Recovery-Grundlage. PR-Recovery verwendet primär die
notierte PR-Nummer und verifiziert Head, Base und Revision; ein
backendneutraler Body-Marker dient nur als Fallback für das Fenster vor der
Notierung.

Repository-Hooks formatieren Candidatecode dadurch nicht mehr still.
Formatierung ist bei Bedarf ein expliziter kontrollierter Pipelineschritt.
Erforderliche Commit-Signierung wird über `commit-tree -S` und eine getrennte
Identitäts-/Transportumgebung bereitgestellt; ohne konfigurierte Fähigkeit
blockiert `signing.required` fail-closed.

## Ownership, Speicher und Aufräumen

Ein mutierbarer Worktree besitzt einen OS-Lock. Der mit #633 aktivierte
Resume-Pfad prüft zuerst diesen Lock, danach ein persistentes Lease und erst
dann sein Zustandsprädikat. Gits eigene Sperre gegen denselben Branch in zwei
Worktrees bleibt eine zweite prozessunabhängige Grenze. Healing verwendet
denselben Run-Worktree.

Kapazitätsplanung misst den Peak eines gleichzeitig vorhandenen Run- und
Verifikations-Worktrees. Vor einem Lauf erfolgt ein konservativer
Freiplatzcheck mit transaktionaler Registrybuchung; eine atomare
Dateisystemreservierung wird nicht behauptet. Quarantänen besitzen eigene
kurze Retention sowie Anzahl-/Größenobergrenzen. Ist die Grenze erreicht,
startet kein neuer Lauf; Evidence wird nicht still gelöscht.

`git worktree prune` ist Teil des Managers und darf aktive oder
quarantänisierte Registryeinträge nie treffen. Automatisch entfernt werden nur
eindeutig terminale, nicht quarantänisierte Bäume und verwaiste Metadaten.

## Konsequenzen

- Die bestehende Gate-11-Fähigkeit wird wiederverwendet; es entstehen nicht
  zwei Worktree-Manager.
- Harte Abbrüche kontaminieren nicht mehr den Hauptcheckout, sondern werden
  zu Resume- oder Garbage-Collection-/Quarantänefällen.
- Lokale unversionierte Abhängigkeiten werden nicht mehr implizit sichtbar.
  Toolchains und Caches müssen vor Rollout gemessen und explizit gebunden
  werden.
- Multi-Prozess-Isolation wird mit realen konkurrierenden Prozessen belegt,
  nicht durch einen synchronen Semaphore-Test.
- #633/#482-Teilschritt 4 aktiviert restartfähige Finalisierung auf Grundlage
  dieses umgesetzten Vertrags; LLM-Runden bleiben davon ausgeschlossen.
- Die Prozesssandbox bleibt der getrennte Vertrag #619.

## Rollout-Grenze

Die Entscheidung allein aktivierte keine Worktrees. Vor der Aktivierung wurden
Peak-Speicher und Laufzeit auf der Referenzhardware, linked-Worktree-Verhalten
gegen #603, fehlende unversionierte Inputs, Lock-/Crashfenster, Quarantäne und
Prune sowie Signierungs- und Hookverhalten positiv und fail-closed negativ
nachgewiesen. #618 aktivierte den gemeinsamen Manager; #633 verwendet seine
OS-Lock-/Registry-/Quarantänegrenze für gebundenes Finalisierungs-Resume.
