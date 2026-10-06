#!/usr/bin/env bash
# S.A.M.U.E.L. — Entwicklungscheckout-Bootstrap (#402/#706).
# git clone … && cd … && ./install.sh
# Legt eine venv an, installiert das Paket und startet danach den Setup-Wizard.
# Kein In-place-Kundenupdate: Releaseinstallationen verwenden ADR-0706 und
# ``samuel-release`` mit einer neuen versionierten Geschwister-venv.
set -euo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
EXTRAS="${SAMUEL_EXTRAS:-[all]}"

echo "==> S.A.M.U.E.L. Entwicklungscheckout-Installer"

# 1) Python-Version prüfen (>= 3.10)
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "FEHLER: $PY nicht gefunden. Python >= 3.10 installieren." >&2
  exit 1
fi
"$PY" - <<'PYEOF'
import sys
if sys.version_info < (3, 10):
    sys.exit(f"FEHLER: Python >= 3.10 noetig, gefunden {sys.version.split()[0]}")
PYEOF

# 2) venv anlegen (falls nicht vorhanden)
if [ ! -d .venv ]; then
  echo "==> Lege virtuelle Umgebung an (.venv)"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 3) Paket + Extras installieren
echo "==> Installiere Paket (Extras: ${EXTRAS})"
pip install --upgrade pip >/dev/null
pip install -e ".${EXTRAS}"

echo "==> Erzeuge lokales Entwickler-Wiki (wiki/)"
"$PY" tools/wiki.py build

echo
echo "==> Installation fertig."

# 4) Setup: non-interaktiv wenn SCM_* gesetzt (Automatisierung), sonst Wizard.
if [ "${SAMUEL_SETUP:-}" = "auto" ] || { [ -n "${SCM_URL:-}" ] && [ -n "${SCM_TOKEN:-}" ] && [ -n "${SCM_REPO:-}" ]; }; then
  echo "==> SCM-Variablen erkannt — non-interaktives Setup"
  samuel setup --non-interactive
else
  echo "Naechster Schritt:  source .venv/bin/activate && samuel setup"
  echo "(oder Variablen SCM_URL/SCM_TOKEN/SCM_REPO setzen und ./install.sh erneut fuer Auto-Setup)"
fi
