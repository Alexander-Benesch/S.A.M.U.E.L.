# Drift History and Lessons

Dieses Dokument trennt aktuelle Regeln von datierter Evidence. Es weist keine
Schuld zu; es macht wiederholbare Vor-Run-Pruefungen explizit.

| Phase / Driftklasse | Soll und abweichender Zustand | Entdeckung, Auswirkung und heutige Gegenmassnahme |
|---|---|---|
| Qualification-Harness vs. Product | oeffentliche Productpfade; zeitweise Helper, direkter Containerstart oder interne Wirkung | reale Prep-/E2E-Readbacks; technische Erfolge waren nicht qualificationfaehig. Runbook bindet Production-Compose und Public Flow; #900 bleibt offen |
| lokaler vs. Gitea SHA | Gitea `main` ist zuerst Product-Wahrheit; lokale Handoffs waren hinterher | Fetch-/Mergebase-Readback; falsche Claims/Tests drohten. Vor Mutation Snapshot, Fetch, Safety-Ref/Stash und `--ff-only` |
| historische Evidence als aktuelle Wahrheit | datierte Audits sind Snapshots; sie wurden teils wie heutige Capability gelesen | Code-/Test-Gegenpruefung; Statusdrift. Jede neue Aussage traegt CURRENT/HISTORICAL/OPEN-Klasse |
| Config/Route vs. Runtime | gespeicherte Route oder Digestgleichheit wurde mit aktiver Wirkung verwechselt | reale Providercalls; 401, unavailable oder Truncation. Bounded Probe jeder effektiven Taskroute vor positivem Run |
| Provideravailability/Truncation | konfiguriertes Modell sollte erreichbar und passend sein; dieselbe historisch problematische Route wurde erneut verwendet | Issue #2 endete wieder am 8192-Outputlimit. Provider-Evidence vor Subject pruefen; Routewechsel ist neuer Input |
| `.env`/Compose/Secrets | kanonische Parser-/Compose-Semantik; ad-hoc Split und Materializer veraenderten Werte/Startpfad | 401-Gegenproben und Startpfad-Review. Keine eigene Parsinglogik; keine Secretwerte oder Fingerprints in Evidence |
| Freshness/Subject | neuer sauberer lokaler State wurde mit isoliertem SCM-Subject verwechselt | Watch sah historische Issues. Disposable, gebundenes Repo plus Branch/Issue/PR-Readback vor Start |
| Label-Provisioning | alle erforderlichen konfigurierten Semantik-Mappings vor Workflowwirkung | frisches Repo hatte 0/15 Labels und Planstatus konnte nicht materialisiert werden. `setup-labels` plus exakter Readback; fremde Labels bleiben erlaubt |
| Runner-Autodetection | explizite oder belastbar erkannte Runnerpolicy | `pyproject.toml` autorisierte faelschlich Pytest fuer ein unittest-Projekt. #754/#756 und gemeinsame Resolverregression; Doctor/Preflight vor Tokens |
| Prompt/Parser/Acceptance | Promptbeispiele und Parsergrammar muessen identisch sein | Backticks/Selektoren und unmoegliches `GREP:NOT` blockierten spaet. #902/#916; Contractretry und Precheck vor Human Approval |
| Human Approval Transport | echte, gebundene Humanentscheidung; Label allein ist keine Authority | Webhook-/Pollingunterschiede und native Gitea-Events. #904 und durable Authority; beide Transporte getrennt ausweisen |
| Durable Approval vs. Statuslabels | Authority ueberlebt Projektion, Gate-Fail und Restart | Freigabe ging historisch bei Labeluebergang verloren. #895 plus Tests; Replan widerruft explizit |
| MANUAL Continuation | gueltiger Receipt dispatcht Reevaluation | Issue #3 lieferte nur `IssueCommented`. #910/PR #911 plus Restart-/Replayregression; alter Run bleibt FAIL |
| Wiki/README/Release | aktive Doku bindet aktuellen Code, Historie bleibt datiert | mehrere alte Versions-/Schema-/Capabilityclaims. Document-/Wiki-Vertrag und Statusindex; Publish erst nach Docs-Merge |
| run-lokale Regeln | Productauthority kommt aus versioniertem Contract, nicht aus 3x100-/Helperwissen | Qualificationnotizen wurden als allgemeine Norm gelesen. Run-lokale Regeln als Evidence markieren und nicht in Productcode projizieren |

## Bereits gefunden und spaeter erneut gemacht

Wiederholt wurden bekannte Providertruncation, statische statt reale
Route-Readiness, unvollstaendige Preparation, Vermischung von Impacttest und
vollstaendigem Rehearsal sowie lokale/remote Freshnessannahmen. Auch nach der
ersten MANUAL-/Approvalanalyse wurden Transport, durable Authority und
Continuation in spaeteren Attempts erneut als eine einzige Grenze behandelt.
Die Wiederholung entstand vor allem, weil Vorbedingungen schrittweise waehrend
des Runs entdeckt statt vor dem Subject als geschlossene Readinessmatrix
geprueft wurden.

## Verbindliche Vor-Run-Pruefung

1. Product-, Demo-, Config-, Policy- und Runner-SHAs/Digests aufzeichnen.
2. frischen, watch-isolierten SCM-Subject samt leerer/erwarteter Issue- und
   PR-Menge bestaetigen.
3. Required Checks, Branch Protection, Webhooksignatur/Eventtypen und alle
   benoetigten S.A.M.U.E.L.-Mappings read-only pruefen; fehlende eigene Labels
   explizit provisionieren und erneut lesen.
4. Runtimeuser, Mounts, Data-/Workspacepfade, Stateintegritaet und freien Platz
   mit der echten Prozessidentitaet pruefen.
5. kanonischen Setup-/Compose-Startpfad nutzen; keine Secrets transformieren.
6. jede effektive LLM-Taskroute bounded real pruefen, einschliesslich
   Antwortschema und Output-Suitability.
7. Runnerart, Binary und Selectorgrammar aus derselben Core-Policy pruefen, die
   Planning und Gate 11 verwenden.
8. erst danach `READY` erklaeren; waehrend des Runs keine neuen Vorbedingungen
   nachschieben oder den Subject intern reparieren.

Automatische Praevention ist mit Contracttests, Main-CI, Source-Digests,
State-/Authoritybindungen und Regressionen weit ausgebaut. Der vollstaendige
komponierte Self-Check (#921), der einheitliche Re-Entry-Vertrag (#920) und die
reale Golden-/D0-Qualification (#859/#658) fehlen weiterhin.
