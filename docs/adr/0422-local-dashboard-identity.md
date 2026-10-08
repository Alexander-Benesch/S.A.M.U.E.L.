---
id: ADR-0422
title: Lokaler Dashboard-Identity-Provider und expliziter Legacy-Cutover
status: accepted
decision_issue: 422
decision_date: 2026-09-18
decision_digest: sha256:2346d1b9257fd5afc318d625683bbcd408198be0a2c325d2693a6afa3bc2eec9
supersedes: []
superseded_by: []
---

# Lokaler Dashboard-Identity-Provider und expliziter Legacy-Cutover

## Kontext

Der globale `SAMUEL_API_KEY` unterscheidet weder Menschen noch Rollen und
erlaubt keine personenbezogene Attribution, selektive Sitzungswiderrufe oder
minimale Rechte. #422/D09–D13 verlangen für eigenständige Installationen einen
sicheren lokalen Referenzprovider. Eine allgemeine IAM-, OAuth-, PKI- oder
Pairing-Plattform gehört gemäß ADR-0678 nicht zum Produktkern.

## Entscheidung

S.A.M.U.E.L. liefert vier unabhängige, kombinierbare Rollen aus: Viewer sieht
nur den reduzierten Dienststatus; Auditor liest Audit-, Security- und
Diagnosenachweise; Operator führt Workflow- und Provideroperationen aus;
Administrator verwaltet Konfiguration, lokale Identitäten und Sitzungen. Jeder
HTTP-Endpunkt besitzt eine konkrete Permission. Rollen bilden keine Hierarchie.
Automation verwendet separat erzeugte opaque Bearer-Token mit expliziter
Permissionmenge und Ablaufzeit.

Der Referenzprovider speichert Benutzer, Argon2-Passworthashes, Rollen, opaque
Sitzungs- und CSRF-Hashes, Automation-Tokenhashes sowie Widerrufe im vorhandenen
SQLite-State. Sitzungen sind an Instanz-UUID und Credential-Version gebunden,
laufen absolut nach acht Stunden und bei dreißig Minuten Inaktivität ab.
Identitätsänderungen verlangen eine höchstens fünf Minuten alte
Passwortauthentisierung. Browser-Sitzungen verwenden HttpOnly- und
SameSite-Strict-Cookies; schreibende Requests benötigen einen CSRF-Wert. Unter
HTTPS wird das Secure-Attribut konfiguriert.

Restore widerruft alle Sitzungen und Automation-Token und setzt den
Identity-State auf `recovery_pending`. Nur der lokale CLI-Recoverypfad aktiviert
ihn erneut. Bootstrap und Recovery lesen das Passwort aus einer regulären, dem
aufrufenden OS-Benutzer gehörenden Datei mit Modus 0600 oder strenger. Sie
teilen Lifecycle-Lock und Authority-Epoch/Witness; es entsteht keine zweite
Autoritätsserie.

`config/auth.json` wählt genau einen Modus. `legacy_api_key` startet ohne
`SAMUEL_API_KEY` fail-closed. `local_identity` akzeptiert den alten Key niemals
als Fallback. Der CLI-Cutover verlangt einen aktiven lokalen Administrator,
eine bestätigte Client-Inventur und eine Begründung und ersetzt die
Konfiguration atomar.

## Konsequenzen und Grenzen

Lokale Identität erteilt keine Operator-Konfigurationsauthority und hebt den
Production-Freeze aus #691 nicht auf. Identity-Aktionen werden mit Akteur und
sachlichen Metadaten über den vorhandenen Auditpfad protokolliert; Passwörter,
Rohsessions, CSRF-Werte und Roh-Token werden nie protokolliert oder in Diagnosen
ausgegeben. Identity-Tabellen sind konservativ im Retention-/DSGVO-Katalog
klassifiziert.

Der lokale Provider ist die mitgelieferte Referenzimplementierung. Eine externe
Identity-Grenze entsteht erst mit einem realen zweiten Provider oder einer
gesonderten Security-Anforderung. OAuth, OIDC, LDAP, allgemeines IAM,
Mandantenverwaltung, Passwort-Reset per E-Mail und Account-Self-Service sind
nicht Teil dieser Entscheidung.

Unit- und HTTP-Integrationstests belegen den Codevertrag. Die betriebliche
Qualification von HTTPS/Secure-Cookies, Migration, Neustart, Restore/Recovery,
Widerruf und Rollenwirkung auf der D0-Referenzinstallation bleibt vor dem
Schließen von #422 erforderlich.

## Verworfene Alternativen

- stiller API-Key-Fallback nach lokalem Cutover;
- hierarchische Rollen mit implizit geerbten Rechten;
- Session- oder Passwortmaterial im Browser-Storage;
- allein durch Loopback legitimierter Bootstrap oder Recovery;
- eine parallele Identity-Datenbank, Epoch oder Auditspur;
- vorgezogene OAuth-/IAM-/Pairing-Abstraktion ohne zweiten realen Provider.
