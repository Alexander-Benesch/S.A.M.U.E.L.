---
id: ADR-0619
title: Fail-closed Sandboxvertrag für kandidatenkontrollierte Ausführung
status: superseded
decision_issue: 619
decision_date: 2026-08-29
decision_digest: sha256:2c3b0ed956372ba3161324d07ea76bbb995e81474725917363734034bf130490
supersedes: []
superseded_by: ["ADR-0678"]
---

# Fail-closed Sandboxvertrag für kandidatenkontrollierte Ausführung

> **Superseded am 30. August 2026 durch ADR-0678 / #678 und den
> Nachfolgescope #679.** Das hier beschriebene Securityfinding bleibt für den
> aktuellen lokalen Legacy-Pfad wahr. Verworfen wurde der Bau eines eigenen
> S.A.M.U.E.L.-Sandbox-Ports; Candidate-Ausführung soll stattdessen an einen
> austauschbaren Execution-/CI-Provider delegiert und über gebundene Evidence
> bewertet werden. Dieser Text bleibt als historische Entscheidungsstufe
> unverändert nachvollziehbar.

## Kontext

#612 bindet TEST-Runner und Timeout an den vertrauenswürdigen Control-Plane-
Snapshot. #613 startet IMPORT- und TEST-Kindprozesse mit einer sterilen
Environment-Allowlist ohne geerbte SCM-, LLM-, Signing-, Cloud-, SSH- oder
Git-Zugangsdaten. Gate 11 führt diese Prozesse in einem detached Worktree des
Candidate-Heads aus.

Diese Schichten begrenzen Herkunft, Environment und Dateistand, aber keine
OS-Rechte. Candidate-Testdateien und importierte Candidate-Module bleiben
LLM-geschriebener ausführbarer Code. Mit den Rechten des Agentbenutzers können
sie grundsätzlich andere lesbare Hostdateien und Prozessinformationen lesen,
Netzwerkverbindungen öffnen und CPU, RAM, PIDs, Dateideskriptoren oder Speicher
verbrauchen.

Ein Worktree und eine Environment-Allowlist sind deshalb keine Sandbox. Eine
Mechanismenwahl allein aus Produktdokumentation wäre im LXC-Referenzbetrieb
ebenfalls keine belastbare Wirksamkeitsaussage.

## Vorgeschlagene Entscheidung

Jede kandidatenkontrollierte IMPORT-/TEST-Ausführung muss durch einen
backendneutralen Sandbox-Port laufen. Der Port beschreibt Fähigkeiten und
Fehlerverhalten, nicht Docker-, LXC- oder systemd-Befehle. Ein fehlender oder
nicht beweisbar wirksamer Adapter blockiert die betreffende automatische
Evidence fail-closed; es gibt keinen stillen Rückfall auf Ausführung im
Hostprozess.

Der konkrete Linux/LXC-Referenzadapter wird erst nach einem Live-Spike auf der
Referenzhardware ausgewählt. Dieser ADR bleibt bis zur dokumentierten Messung
und Mechanismenentscheidung `proposed`. Andere Plattformen können einen
konformen Adapter bereitstellen oder müssen die Capability als nicht verfügbar
melden.

## Vertrauensgrenze

Außerhalb des Candidate-Namespace bleiben:

- installierter Agentcode und Agentinterpreter,
- Gate-, Eval-, Architektur-, Runner- und Security-Policy,
- Sandbox-Manager und Lifecycle,
- SCM-/Push-/Signing-Transport und seine Credentials,
- `agent.data_dir`, Audit-/State-Store und Operator-Home.

Der Candidate-Checkout wird nur als Arbeitsinput eingebracht. Der Agent
importiert oder startet Candidatecode nicht außerhalb des Sandbox-Ports, auch
nicht im Self-Mode. #612 und #613 bleiben die einzigen Quellen für
Runner/Timeout beziehungsweise Environment; die Sandbox kapselt diese
Verträge, statt sie zu duplizieren.

## Mindestfähigkeiten

Ein konformer Adapter muss folgende Grenzen gemeinsam nachweisen:

- **Dateisystem:** minimaler Runtimebestand, enumerierte Schreibpfade,
  beschränktes Temp und kein Zugriff auf Operator-Home, Agent-State,
  Agentinstallation, Docker-Socket, beliebige Hostpfade oder Host-`/proc`.
- **Netzwerk:** Default deny. Ausnahmen sind explizit, ziel-/zeitbegrenzt und
  policyversioniert; SCM-, LLM-, Metadata- und Homelab-Control-Plane-Endpunkte
  bleiben unzugänglich.
- **Prozess/Benutzer:** unprivilegierte Identität, keine zusätzlichen
  Capabilities, kein Host-PID-Namespace und keine Eskalations-, Mount- oder
  Namespace-Rechte.
- **Ressourcen:** harte Grenzen für Walltime, CPU, RAM, PIDs/Threads,
  Dateideskriptoren, Output und beschreibbaren Speicher. Überschreitung beendet
  den vollständigen Prozessbaum.
- **Evidence:** Sandboxprofil und -version, Adapter, effektive Limits und ein
  klassifizierter Exitgrund werden gebunden ausgegeben, aber keine Secrets,
  unbeschränkten Logs oder unnötigen Hostpfade.

Push- und Signing-Schlüssel werden nie über eine vermeintlich kontrollierte
Workspace-Environment in den Candidate-Namespace gereicht. Signierung bleibt
eine getrennte vertrauenswürdige Identitäts-/Transportaktion.

## Plattform- und Betriebsvertrag

`samuel doctor` oder ein gleichwertiger Healthcheck muss die effektive
Sandboxfähigkeit durch reale Negativproben belegen, nicht nur durch das
Vorhandensein eines Binaries. Container-, systemd- und direkter CLI-Betrieb
dokumentieren getrennt, wie dieselbe Grenze verankert ist. Ein nur in einem
Betriebspfad wirksamer Adapter darf nicht global als aktiv erscheinen.

Vor der Annahme dieses ADR werden auf dem unprivilegierten LXC mindestens
User-, Mount-, PID- und Network-Namespace-Fähigkeiten, cgroup-v2-Controller,
Netzwerk-Default-Deny, Prozessbaum-Abbruch, notwendige Toolchain-/Cache-Mounts
und Start-/Testkosten live gemessen. Ein privilegierter Docker-Socket oder das
Weiterreichen von Host-Credentials ist kein zulässiger Referenzadapter.

## Konsequenzen

- Policy-Herkunft (#612), Environment-Härtung (#613), Worktree-Lifecycle
  (#618) und Prozesssandbox bleiben getrennte, komplementäre Schichten.
- Weniger Candidate-Ausführung durch die Preflight-Neuordnung #620 bleibt
  unabhängig sinnvoll und ist keine Sandboxvoraussetzung.
- Plattformen ohne konformen Adapter verlieren automatische IMPORT-/TEST-
  Evidence, statt sie unsandboxed zu erzeugen.
- Die Sandbox kann Laufzeit und Speicher erhöhen; Kosten und verfügbare
  Toolchains sind Teil der Annahmeevidence.
- Subject-/Policy-Digest, Audit, Health, Dashboard und Betriebsdokumentation
  müssen das tatsächlich aktive Sandboxprofil ausweisen.

## Annahmekriterium

Der Status darf erst auf `accepted` wechseln, wenn ein nach den
Repositoryregeln ausgegliederter Folge-ADR oder eine explizite Revision mit
neuem Decision-Digest den ausgewählten Referenzadapter, die gemessenen
Kernel-/LXC-Voraussetzungen, positive und negative Drills sowie das
fail-closed Plattformfallback festlegt. Eine fehlende Messung ist kein Grund,
unsandboxed Hostausführung länger als sicher darzustellen.
