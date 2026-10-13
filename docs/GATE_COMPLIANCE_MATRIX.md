# Gate-/Compliance-Matrix — Kompatibilitätshinweis

Die frühere manuell gepflegte Tabelle wurde durch die versionierte
[Capability-/Wirksamkeitsmatrix](CAPABILITY_MATRIX.md) ersetzt. Deren
maschinenlesbare Quelle ist
[`docs/capabilities/control-matrix.json`](capabilities/control-matrix.json).

Diese Datei bleibt als stabiler Einstieg für bestehende Links erhalten. Sie ist
keine zweite Quelle für Gate-Namen, Profilstatus, Prüftiefe oder
Compliance-Claims.

Quellenhierarchie:

1. Code bestimmt das tatsächliche Verhalten.
2. `config/gates*.json`, Workflows und SCM-Regeln bestimmen Aktivierung und
   Enforcement.
3. Die Capability-Matrix bewertet Wirksamkeit, Evidence, bekannte Lücken und
   öffentliche Claims.
4. `docs/RUNTIME_REFERENCE.md` erzeugt verfügbare und ausgeliefert konfigurierte
   Runtime-Fakten direkt aus Code und Config; effektive Betreiber-Overrides
   brauchen weiterhin einen Betriebsnachweis.
5. `docs/CAPABILITY_MATRIX.md` wird deterministisch aus der Control-Matrix
   erzeugt.

Die Zuordnung zu OWASP- und EU-AI-Act-Artikeln ist Kontext für die eigene
Risikobewertung, kein Compliance-Nachweis. Die SemVer des ersten Releases
wurde im abgeschlossenen Dachissue #479 festgelegt.

<!-- Historischer Inhalt entfernt: #517 verhindert damit eine parallel
     gepflegte, abweichende Gate-Tabelle. -->
