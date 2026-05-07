# Premium-Plugin Setup

Operator-Anleitung für das Aktivieren von Premium-Features (LLM-Routing per Task, API-Key-Validation gegen Provider-Endpoints) in einer SAMUEL-Installation.

## Konzept

SAMUEL läuft standardmäßig im **free mode** (manueller LLM-Provider, keine Routing-Schicht, kein Crypto). Premium-Features sind hinter Ed25519-signierten, lifetime-gültigen Lizenzen gegated:

- License-Issuer (du) hält den **Private-Key** offline
- License-Empfänger (Kunde) bekommt eine signierte JSON-Datei
- Code verifiziert beim Boot mit dem **eingebetteten Public-Key**
- Bei ungültiger/fehlender Lizenz: free mode (graceful)

## Einmaliger Setup (Operator)

### 1. Keypair generieren

```bash
python tools/generate_keypair.py
```

Output:
```
PRIVATE_KEY_HEX: <64 hex chars>
PUBLIC_KEY_HEX:  <64 hex chars>
```

### 2. Private-Key offline speichern

```bash
mkdir -p ~/.samuel
echo "<PRIVATE_KEY_HEX>" > ~/.samuel/license-private.key
chmod 600 ~/.samuel/license-private.key
```

**Niemals** in das Repository committen. `.gitignore` hat `license-private.key` bereits ausgeschlossen.

### 3. Public-Key im Code einbetten

`samuel/core/license.py`:
```python
LICENSE_PUBLIC_KEY_HEX = "<PUBLIC_KEY_HEX>"
```

Committen + pushen. Der Public-Key ist im Repo OK — er kann nur verifizieren, nicht signieren.

## Pro Kunden-Anfrage (~30 Sekunden)

```bash
python tools/generate_license.py \
    --email customer@example.com \
    --features llm_routing,api_validate \
    --private-key ~/.samuel/license-private.key \
    --out customer_license.json
```

Output (`customer_license.json`):
```json
{
  "email": "customer@example.com",
  "features": ["api_validate", "llm_routing"],
  "issued_at": "2026-05-05T14:34:18Z",
  "signature": "<base64-Ed25519-Sig>"
}
```

Mail an Kunden. Kunde aktiviert wahlweise:

**Variante A — File:**
```bash
cp customer_license.json /path/to/samuel/config/license.json
```
`config/license.json` ist in `.gitignore` — wird nicht versehentlich committed.

**Variante B — Env var (CI/Docker):**
```bash
export SAMUEL_LICENSE_KEY="$(cat customer_license.json)"
```

Env-Variable hat Vorrang vor File.

## Verifikation

```bash
samuel --self health
```

Erwartete Ausgabe bei aktiver Lizenz:
```
Premium: active (license: customer@example.com, features: api_validate, llm_routing)
```

Bei free mode:
```
Premium: free mode (no valid license)
```

Im Dashboard sichtbar unter Tab **Settings**, oberste Card "Premium":
- Aktiv: grüner Badge `PREMIUM aktiv` mit Email + Feature-Liste
- Free: gelber Badge `FREE MODE` mit Reason

## Verfügbare Features

Aktuelle Feature-Tokens:

| Token | Wirkung |
|---|---|
| `llm_routing` | (legacy, seit #301 nicht mehr nötig — statisches Per-Task ist FREE) |
| `llm_routing_advanced` | Time-Window-`schedule`-Block (Tag/Nacht-Switch pro Task) — siehe #302 |
| `llm_routing_dashboard_write` | Dashboard Settings-Tab Inline-Editor pro Task (Provider/Model/system_prompt) — siehe #309. Auch fuer System-Prompt-Edit (#315) erforderlich. |
| `api_validate` | (zukünftig) Live-Validation der API-Keys gegen Provider-Endpoints im Dashboard |

`premium` und `all` als Feature-Tokens werden NICHT akzeptiert — Lizenzen müssen explizit Feature-Listen angeben.

## Troubleshooting

| Symptom | Ursache | Fix |
|---|---|---|
| `Premium: free mode (no license public key configured)` | Schritt 3 nicht gemacht (Public-Key leer) | `LICENSE_PUBLIC_KEY_HEX` setzen, neu starten |
| `Premium: free mode (no valid license)` | Datei fehlt oder Signatur ungültig | License regenerieren, Public-Key-Match prüfen |
| `License invalid (InvalidSignature: ...) — running in free mode` (Log) | License gegen alten Public-Key signiert | Neue License generieren mit aktuellem Private-Key |
| `LLM-TaskRouting: skipped (no premium license / feature missing)` | Lizenz aktiv, aber `llm_routing` nicht in `features` | License regenerieren mit `--features llm_routing` |

## Sicherheits-Hinweise

- Private-Key NIEMALS committen oder via Git/Email weitergeben
- License-Files sind kunden-spezifisch — bei Customer-Wechsel neu signieren
- Es gibt keine Revocation-Liste — kompromittierte Lizenzen sind invalid erst nach neuem Keypair (würde alle Kunden ausstoßen)
- Honor-System: Kunde könnte License an Dritte weitergeben — die Email im JSON ist nur Audit-Trail, nicht Hard-Enforcement

## Verwandte Dokumente

- `docs/OPERATING_RULES.md` R-Kapitel für Operator-Workflows
- Issue #294 — Foundation
- Issue #225 — TaskRouting (Premium-gated)
- Issue #211 — API-Key-Validation
- Issue #204 — Settings-UI

## Feature: `llm_routing_advanced` (#302)

**Time-Window-Routing** — pro Task ein optionaler `schedule`-Block, der
provider/model nach Tageszeit ueberlagert. Mitternacht-Uebergang wird korrekt
behandelt.

Beispiel `config/llm/defaults.json`:

```json
{
  "tasks": {
    "implementation": {
      "provider": "deepseek",
      "model": "deepseek-coder",
      "schedule": {
        "active": true,
        "from": "22:00",
        "to": "06:00",
        "provider": "claude",
        "model": "claude-opus"
      }
    }
  }
}
```

Tagsueber: `deepseek-coder`. Nachts (22:00 bis 06:00): `claude-opus`.

**Aktivieren:**
```bash
python tools/generate_license.py \
    --email customer@example.com \
    --features llm_routing,llm_routing_advanced \
    --private-key ~/.samuel/license-private.key
```

Ohne dieses Feature in der Lizenz: `schedule`-Bloecke werden silent ignoriert,
statisches Routing bleibt aktiv (siehe #301).

## Provider: `openrouter` (#318)

**OpenRouter-Gateway** — ein einziger API-Key gibt Zugriff auf 350+ Modelle aller grossen Provider (Anthropic, OpenAI, Google, DeepSeek, ...) ueber `https://openrouter.ai/api/v1`.

**Vorteile:**

- **Unified Billing**: eine Rechnung statt einer pro Provider
- **Balance abrufbar**: `validate()` liefert `balance` direkt aus `GET /auth/key`
- **Model-Discovery automatisch**: alle 350+ Modelle aus dem `samuel/adapters/llm/costs.py`-Cache (gleicher Cache, der fuer Pricing genutzt wird)
- **Kein Provider-Key-Management**: ein Key statt N

**Tradeoffs:**

- ~50ms Gateway-Latenz
- ~5% Markup auf Modell-Preise
- Lokale Provider (Ollama/LMStudio) gehen NICHT ueber OpenRouter

**Setup:**

1. API-Key auf `https://openrouter.ai/keys` erstellen
2. In `.env`:
   ```bash
   OPENROUTER_API_KEY=sk-or-v1-...
   ```
3. In `config/llm/defaults.json`:
   ```json
   {
     "tasks": {
       "implementation": {
         "provider": "openrouter",
         "model": "anthropic/claude-sonnet-4-6"
       },
       "review": {
         "provider": "openrouter",
         "model": "deepseek/deepseek-chat"
       }
     }
   }
   ```
   Modell-IDs nutzen das `vendor/model`-Format. Im Dashboard Settings-Tab ist der Models-Dropdown beim Provider `openrouter` mit allen 350+ Modellen befuellt.

**Free vs. Premium:**

OpenRouter selbst ist NICHT premium-gated — der Adapter funktioniert ohne Lizenz, die statische Per-Task-Konfiguration ist FREE (#301). Premium-gated ist nur der Inline-Editor (`llm_routing_dashboard_write`) und das Schedule-Feature (`llm_routing_advanced`).