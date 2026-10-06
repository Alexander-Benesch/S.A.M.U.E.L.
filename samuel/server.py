from __future__ import annotations

import ipaddress
import json
import logging
import os
from html import escape as escape_html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from samuel import __build_info__
from samuel.adapters.api.auth import APIKeyAuth, AuthRuntimeConfig, DashboardAuth
from samuel.adapters.api.rest import RestAPI
from samuel.adapters.api.webhooks import WebhookIngressAdapter
from samuel.adapters.auth.local import LocalIdentityService
from samuel.core.bus import Bus
from samuel.core.identity import AuthenticatedActor, IdentityError
from samuel.slices.dashboard.handler import DashboardHandler
from samuel.slices.setup.handler import SetupHandler

log = logging.getLogger(__name__)

_PRODUCT_VERSION_MARKER = "__SAMUEL_PRODUCT_VERSION__"

DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>S.A.M.U.E.L. Dashboard</title>
<script>try{document.documentElement.dataset.theme=localStorage.getItem('samuel-theme')||'dark';}catch(e){document.documentElement.dataset.theme='dark';}</script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{color-scheme:dark;--page:#0f172a;--surface:#1e293b;--surface-strong:#020617;--text:#e2e8f0;--muted:#94a3b8;--faint:#64748b;--border:#334155;--border-hover:#475569;--accent:#38bdf8}
html[data-theme="light"]{color-scheme:light;--page:#f1f5f9;--surface:#ffffff;--surface-strong:#e2e8f0;--text:#0f172a;--muted:#475569;--faint:#64748b;--border:#cbd5e1;--border-hover:#94a3b8;--accent:#0369a1}
body{font-family:system-ui,-apple-system,sans-serif;background:var(--page);color:var(--text);padding:1.5rem;max-width:1200px;margin:0 auto;transition:background .2s,color .2s}
header{display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;flex-wrap:wrap;gap:.5rem}
header h1{font-size:1.5rem;color:var(--accent)}
header h1 span{font-size:.75rem;color:var(--faint);font-weight:400;margin-left:.5rem}
.meta{font-size:.75rem;color:var(--faint);text-align:right}
.countdown{font-size:.7rem;color:var(--faint)}
.tabs{display:flex;gap:2px;margin-bottom:1rem;border-bottom:2px solid var(--border);overflow-x:auto}
.tab{background:transparent;color:var(--muted);border:none;padding:.75rem 1.25rem;cursor:pointer;font-size:.875rem;border-bottom:2px solid transparent;margin-bottom:-2px;white-space:nowrap}
.tab.active{color:var(--accent);border-bottom-color:var(--accent)}
.tab:hover{color:var(--text)}
.tab-content{display:none}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:1rem;margin-bottom:1.5rem}
.card{background:var(--surface);border-radius:8px;padding:1rem;border:1px solid var(--border);transition:border-color .2s}
.card:hover{border-color:var(--border-hover)}
.card h3{font-size:.7rem;color:var(--muted);margin-bottom:.4rem;text-transform:uppercase;letter-spacing:.05em}
.card .val{font-size:1.4rem;font-weight:700}
.ok{color:#4ade80}.warn{color:#fbbf24}.err{color:#f87171}
.section{background:var(--surface);border-radius:8px;padding:1rem;border:1px solid var(--border);margin-bottom:1rem}
.section h2{font-size:.875rem;color:var(--muted);margin-bottom:.75rem;text-transform:uppercase;letter-spacing:.05em}
.health-row{display:flex;justify-content:space-between;padding:.4rem 0;border-bottom:1px solid var(--border);font-size:.85rem}
.health-row:last-child{border-bottom:none}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:.4rem;vertical-align:middle}
.dot.g{background:#4ade80}.dot.r{background:#f87171}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:.5rem .75rem;border-bottom:1px solid var(--border)}
th{color:var(--muted);font-size:.7rem;text-transform:uppercase}
td{font-size:.85rem}
.badge{display:inline-block;padding:.125rem .5rem;border-radius:9999px;font-size:.75rem;font-weight:600}
.badge-ok{background:#065f46;color:#6ee7b7}
.badge-warn{background:#78350f;color:#fcd34d}
.badge-err{background:#7f1d1d;color:#fca5a5}
.badge-info{background:#1e3a5f;color:#93c5fd}
.badge-ready{background:#065f46;color:#6ee7b7}
.badge-planned{background:#1e3a5f;color:#93c5fd}
.badge-implemented{background:#3b0764;color:#d8b4fe}
.badge-pr_created{background:#164e63;color:#67e8f9}
.badge-blocked{background:#7f1d1d;color:#fca5a5}
.filter-bar{display:flex;gap:.5rem;margin-bottom:1rem;flex-wrap:wrap}
.filter-bar select,.filter-bar input,input,select,textarea{background:var(--surface);color:var(--text);border:1px solid var(--border-hover);padding:.5rem;border-radius:4px;font-size:.8rem}
.filter-bar input{flex:1;min-width:150px}
.warn-item{background:#422006;border:1px solid #92400e;border-radius:6px;padding:.75rem;margin-bottom:.5rem;font-size:.85rem}
.warn-item:last-child{margin-bottom:0}
.toggle{position:relative;display:inline-block;width:40px;height:22px;vertical-align:middle}
.toggle input{opacity:0;width:0;height:0}
.toggle .slider{position:absolute;cursor:default;inset:0;background:#475569;border-radius:11px;transition:.2s}
.toggle input:checked+.slider{background:#0ea5e9}
.toggle .slider::before{content:'';position:absolute;height:16px;width:16px;left:3px;bottom:3px;background:#e2e8f0;border-radius:50%;transition:.2s}
.toggle input:checked+.slider::before{transform:translateX(18px)}
.flag-row{display:flex;justify-content:space-between;align-items:center;padding:.6rem 0;border-bottom:1px solid var(--border);font-size:.85rem}
.flag-row:last-child{border-bottom:none}
.setup-form{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:.75rem}
.setup-form label{display:flex;flex-direction:column;gap:.25rem;color:var(--muted);font-size:.78rem}
.setup-form input,.setup-form select{width:100%}
.setup-note{font-size:.8rem;color:var(--muted);line-height:1.45;margin-bottom:.75rem}
.empty{color:var(--faint);font-style:italic;padding:1rem;text-align:center}
.theme-toggle{background:var(--surface);color:var(--text);border:1px solid var(--border-hover);padding:.25rem .55rem;border-radius:4px;font-size:.72rem;cursor:pointer;margin-left:.5rem}
.auth-overlay{position:fixed;inset:0;background:rgba(2,6,23,.78);display:none;align-items:center;justify-content:center;padding:1rem;z-index:1100}
.auth-dialog{width:min(460px,100%);background:var(--surface);color:var(--text);border:1px solid var(--border-hover);border-radius:8px;padding:1rem;box-shadow:0 20px 50px rgba(0,0,0,.45)}
.auth-dialog h2{font-size:1rem;margin-bottom:.6rem}.auth-dialog p{font-size:.8rem;color:var(--muted);line-height:1.45;margin-bottom:.65rem}.auth-dialog input{width:100%;margin-bottom:.45rem}.auth-actions{display:flex;justify-content:flex-end;gap:.45rem;margin-top:.7rem}.auth-actions button{padding:.4rem .7rem;border-radius:4px;border:1px solid var(--border-hover);background:var(--surface-strong);color:var(--text);cursor:pointer}.auth-feedback{min-height:1.2rem;font-size:.78rem;color:var(--muted)}
html[data-theme="light"] [style*="background:#1e293b"],html[data-theme="light"] [style*="background:#020617"]{background:var(--surface)!important}
html[data-theme="light"] [style*="color:#e2e8f0"],html[data-theme="light"] [style*="color:#cbd5e1"]{color:var(--text)!important}
html[data-theme="light"] [style*="color:#94a3b8"]{color:var(--muted)!important}
html[data-theme="light"] [style*="border:1px solid #334155"],html[data-theme="light"] [style*="border-color:#334155"]{border-color:var(--border)!important}
@media(max-width:600px){header{flex-direction:column;align-items:flex-start}.meta{text-align:left}.grid{grid-template-columns:1fr 1fr}}
</style>
</head>
<body>
<header>
 <h1>S.A.M.U.E.L.<span id="product-version">__SAMUEL_PRODUCT_VERSION__</span><span id="build-revision"></span></h1>
 <div class="meta">
  <div>Letztes Update: <span id="last-refresh" data-timezone="UTC">-</span>
   <button id="auto-refresh-btn" onclick="toggleAutoRefresh()" style="background:#1e293b;color:#e2e8f0;border:1px solid #475569;padding:.2rem .5rem;border-radius:4px;font-size:.7rem;cursor:pointer;margin-left:.5rem">auto-refresh: on</button>
   <button id="theme-toggle" class="theme-toggle" onclick="toggleTheme()" aria-label="Farbschema wechseln">Hell</button>
   <button id="auth-logout" class="theme-toggle" onclick="logoutIdentity()" style="display:none">Abmelden</button>
  </div>
  <div class="countdown">Naechstes Update in <span id="countdown">10</span>s</div>
 </div>
</header>
<div id="toast" style="position:fixed;top:1rem;right:1rem;padding:.75rem 1rem;border-radius:6px;font-size:.85rem;display:none;z-index:1000;max-width:400px"></div>
<div id="auth-overlay" class="auth-overlay">
 <div class="auth-dialog" role="dialog" aria-modal="true" aria-labelledby="auth-title" aria-describedby="auth-help">
  <h2 id="auth-title">Dashboard-Anmeldung</h2>
  <p id="auth-help">Zugriffsmodus wird geladen.</p>
  <label id="auth-user-label" for="auth-user" style="display:none;font-size:.8rem">Benutzername</label>
  <input id="auth-user" type="text" autocomplete="username" spellcheck="false" style="display:none">
  <label id="auth-key-label" for="auth-key" style="font-size:.8rem">SAMUEL_API_KEY</label>
  <input id="auth-key" type="password" autocomplete="current-password" spellcheck="false" onkeydown="if(event.key==='Enter')submitApiKey()">
  <div id="auth-feedback" class="auth-feedback" role="status" aria-live="polite"></div>
  <div class="auth-actions"><button type="button" onclick="cancelApiKey()">Abbrechen</button><button id="auth-submit" type="button" onclick="submitApiKey()">Anmelden</button></div>
 </div>
</div>
<nav class="tabs">
 <button class="tab active" onclick="showTab('status')">Status</button>
 <button class="tab" onclick="showTab('llm')">LLM &amp; Kosten</button>
 <button class="tab" onclick="showTab('quality')">LLM Quality</button>
 <button class="tab" onclick="showTab('activity')">Activity</button>
 <button class="tab" onclick="showTab('workflow')">Workflow</button>
 <button class="tab" onclick="showTab('problems')">Probleme</button>
 <button class="tab" onclick="showTab('logs')">Logs</button>
 <button class="tab" onclick="showTab('security')">Security</button>
 <button class="tab" onclick="showTab('compliance')">Compliance</button>
 <button class="tab" onclick="showTab('setup')">Einrichtung</button>
 <button class="tab" onclick="showTab('settings')">Settings</button>
 <button class="tab" onclick="showTab('selfcheck')">Self-Check</button>
</nav>

<!-- TAB: STATUS -->
<div class="tab-content" id="tab-status">
 <div class="grid">
  <div class="card"><h3>Modus</h3><div class="val" id="s-mode">-</div></div>
  <div class="card"><h3>SCM</h3><div class="val" id="s-scm">-</div></div>
  <div class="card"><h3>Health</h3><div class="val" id="s-health">-</div></div>
  <div class="card"><h3>LLM</h3><div class="val" id="s-llm">-</div></div>
  <div class="card" title="Issues whose latest run passed after at least one previous failure"><h3>Recovered Issues</h3><div class="val" id="s-recovered">-</div></div>
 </div>
 <div class="section"><h2>System-Tiles</h2><div class="grid" id="s-tiles" style="grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:.5rem"></div></div>
 <div class="section"><h2>Health-Checks</h2><div id="s-health-details">-</div></div>
 <div class="section"><h2>Retention</h2><div id="s-retention">-</div></div>
 <div class="section"><h2>Activity (Commands / Events)</h2>
  <table><thead><tr><th>Command/Event</th><th>Count</th><th>Errors</th><th>Avg ms</th></tr></thead>
  <tbody id="s-activity"></tbody></table>
 </div>
 <div class="section"><h2>Score-History (letzte 15 Evals)</h2>
  <table><thead><tr><th>Zeit</th><th>Issue</th><th>Beobachtung</th><th>Legacy-Baseline</th><th>Status</th><th>Hinweis</th></tr></thead>
  <tbody id="s-score-history"></tbody></table>
 </div>
 <div class="section"><h2>Runtime-Anomalien (24h, warn/error)</h2>
  <table><thead><tr><th>Zeit</th><th>Level</th><th>Event</th><th>Issue</th><th>Message</th></tr></thead>
  <tbody id="s-anomalies"></tbody></table>
 </div>
</div>

<!-- TAB: LLM & KOSTEN -->
<div class="tab-content" id="tab-llm">
 <div class="grid">
  <div class="card"><h3>Total Calls</h3><div class="val" id="l-calls">-</div></div>
  <div class="card"><h3>Total Tokens</h3><div class="val" id="l-tokens">-</div></div>
  <div class="card"><h3>Total Cost</h3><div class="val" id="l-cost">-</div></div>
  <div class="card"><h3>Konfigurierter Default-Provider</h3><div class="val" id="l-provider">-</div></div>
 </div>
 <div class="section"><h2>Aktuelle LLM-Calls</h2><div id="l-current-calls">Nicht bekannt</div></div>
 <div class="section"><h2>Letzter Call dieser Runtime</h2><div id="l-last-call">Noch kein Call beobachtet</div>
  <p style="font-size:.75rem;color:#94a3b8">Eine erhaltene Antwort ist kein Parser-, Task-, Gate- oder Qualification-PASS. Call-Facts bleiben flüchtig und werden nach Neustart nicht aus alten Budgetreservationen übernommen.</p>
 </div>
 <div id="l-truncations"></div>
 <div class="section" id="l-model-cache"><h2>OpenRouter Modell- und Benchmarkdaten</h2><div class="empty">Laden...</div></div>
 <div class="section"><h2>API-Key-Status</h2>
  <table><thead><tr><th>Provider</th><th>Model</th><th>Status</th><th>Key/URL</th><th>Hinweis</th></tr></thead>
  <tbody id="l-keys"></tbody></table>
 </div>
 <div class="section"><h2>Konfigurierte Routen pro Task</h2>
  <p style="font-size:.75rem;color:#94a3b8">Konfiguration allein belegt weder Nutzung noch Verfügbarkeit. Evaluation besitzt derzeit keinen produktiven LLM-Consumer.</p>
  <div id="l-schedule" style="font-size:.75rem;color:#94a3b8;margin-bottom:.5rem">-</div>
  <table><thead><tr><th>Task</th><th>Provider</th><th>Model</th><th>Content max</th><th>Reasoning</th><th>Benchmark</th><th>temp</th><th>timeout</th></tr></thead>
  <tbody id="l-routing"></tbody></table>
 </div>
 <div class="section"><h2>Token Usage per Task</h2>
  <table><thead><tr><th>Task</th><th>Calls</th><th>Tokens</th><th>Cost</th></tr></thead>
  <tbody id="l-tasks"></tbody></table>
 </div>
 <div class="section"><h2>Token-History (letzte 50 Calls) <span style="font-size:.7rem;color:#64748b;font-weight:400">— hover ueber Details fuer Listen</span></h2>
  <table><thead><tr><th>Zeit</th><th>Provider</th><th>Model</th><th>Task</th><th>in</th><th>out</th><th>reasoning</th><th>cached</th><th>total</th><th>Cost</th><th>Latency ms</th><th>Issue</th><th>Details</th></tr></thead>
  <tbody id="l-history"></tbody></table>
 </div>
 <div class="section"><h2>Quality-Scores (Provider/Model/Task) <span style="font-size:.7rem;color:#64748b;font-weight:400">— neueste gueltige Score-Serie; Calls nur bei exakter Attribution</span></h2>
  <table><thead><tr><th>Provider</th><th>Model</th><th>Task</th><th>Serie</th><th>Serien-Calls</th><th>Unattrib.</th><th>Andere Serien</th><th>Graded</th><th>Passed</th><th>Failed</th><th>Success %</th><th>Avg Score</th><th>Last</th></tr></thead>
  <tbody id="l-quality"></tbody></table>
 </div>
</div>

<!-- TAB: QUALITY (#153) -->
<div class="tab-content" id="tab-quality">
 <div id="q-warnings"></div>
 <div id="q-series" class="section" style="font-size:.78rem;color:#94a3b8">Aktive Score-Serie wird geladen...</div>
 <div class="section"><h2>Heatmap: Provider/Model &times; Task <span style="font-size:.7rem;color:#64748b;font-weight:400">— Zelle = Avg-Score nur der angezeigten Serie; keine Legacy-/Policy-/Formelmischung</span></h2>
  <div id="q-heatmap" style="overflow-x:auto"><div class="empty">Laden...</div></div>
 </div>
 <div class="section"><h2>Matrix (Provider/Model/Task) <span style="font-size:.7rem;color:#64748b;font-weight:400">— letzter Call je Issue; EWMA und Serien-Calls exakt herkunfts-/policy-/formelgebunden</span></h2>
  <table><thead><tr><th>Provider</th><th>Model</th><th>Task</th><th>Serie</th><th>Serien-Calls</th><th>Unattrib.</th><th>Andere Serien</th><th>Graded</th><th>Passed</th><th>Failed</th><th>Success %</th><th>Avg Score</th><th>EWMA</th><th>Last</th></tr></thead>
  <tbody id="q-matrix"></tbody></table>
 </div>
</div>

<!-- TAB: ACTIVITY (#230) -->
<div class="tab-content" id="tab-activity">
 <div class="section">
  <h2>SCM-Activity <span style="font-size:.7rem;color:#64748b;font-weight:400">— reale Repo-Ereignisse via Webhook (auch manuelle UI-/API-Aktionen). Setzt konfigurierte Gitea-Webhooks voraus.</span></h2>
  <div style="margin-bottom:.5rem">Akteur:
   <select id="act-filter" onchange="renderActivity()" style="background:#020617;color:#e2e8f0;border:1px solid #334155;border-radius:3px;padding:.15rem .3rem;font-size:.8rem">
    <option value="all">Bot &amp; Human</option>
    <option value="human">nur Human</option>
    <option value="bot">nur Bot</option>
   </select>
  </div>
  <table><thead><tr><th>Zeit</th><th>Ereignis</th><th>#</th><th>Titel</th><th>Akteur</th><th>Typ</th><th>Quelle</th></tr></thead>
  <tbody id="act-rows"></tbody></table>
 </div>
</div>

<!-- TAB: WORKFLOW -->
<div class="tab-content" id="tab-workflow">
 <div class="section"><h2>Issue Pipeline <span class="hint" id="w-hint" style="font-size:.7rem;color:#64748b;font-weight:400">(Zeile klicken für Detail)</span> <span id="w-recovered" style="font-size:.7rem;color:#10b981;margin-left:.75rem;font-weight:400"></span></h2>
  <table><thead><tr><th>Issue</th><th>Status</th><th>Last Event</th><th>Timestamp</th><th>Runs</th><th>Trend</th></tr></thead>
  <tbody id="w-issues"></tbody></table>
 </div>
 <div class="section" id="w-detail" style="display:none">
  <h2>Issue <span id="wd-num"></span> Detail <button id="wd-close" style="float:right;background:#334155;color:#e2e8f0;border:none;padding:.25rem .6rem;border-radius:4px;cursor:pointer">Schliessen</button></h2>
  <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:.5rem;margin-bottom:1rem">
   <div class="card"><h3>Status</h3><div class="val" id="wd-status">-</div></div>
   <div class="card"><h3>Branch</h3><div class="val" id="wd-branch" style="font-size:.9rem">-</div></div>
   <div class="card"><h3>Qualitätsbeobachtung</h3><div class="val" id="wd-score">-</div></div>
   <div class="card"><h3>LLM Calls</h3><div class="val" id="wd-llm-calls">-</div></div>
   <div class="card"><h3>LLM Tokens</h3><div class="val" id="wd-llm-tokens">-</div></div>
   <div class="card"><h3>LLM Cost</h3><div class="val" id="wd-llm-cost">-</div></div>
  </div>
  <h3 style="font-size:.85rem;color:#94a3b8;margin:1rem 0 .5rem;text-transform:uppercase">Pipeline Stages</h3>
  <div id="wd-stages" style="display:flex;flex-wrap:wrap;gap:.5rem;margin-bottom:1rem"></div>
  <h3 style="font-size:.85rem;color:#94a3b8;margin:1rem 0 .5rem;text-transform:uppercase">Gate Results</h3>
  <table><thead><tr><th>Gate</th><th>Autorität</th><th>Phase</th><th>Status</th><th>Grund</th></tr></thead>
  <tbody id="wd-gate-results"></tbody></table>
  <h3 style="font-size:.85rem;color:#94a3b8;margin:1rem 0 .5rem;text-transform:uppercase">LLM Calls</h3>
  <table><thead><tr><th>Zeit</th><th>Task</th><th>Provider/Model</th><th>Tokens</th><th>Cost</th><th>Latenz</th><th>Guards</th><th>Tools</th><th>Context</th><th>est.&nbsp;Tokens</th></tr></thead>
  <tbody id="wd-llm-detail"></tbody></table>
  <h3 style="font-size:.85rem;color:#94a3b8;margin:1rem 0 .5rem;text-transform:uppercase">Test Runs</h3>
  <table><thead><tr><th>Zeit</th><th>Test</th><th>Runner</th><th>Status</th><th>Dauer</th><th>Exit</th></tr></thead>
  <tbody id="wd-test-runs"></tbody></table>
  <h3 style="font-size:.85rem;color:#94a3b8;margin:1rem 0 .5rem;text-transform:uppercase">Acceptance Checks</h3>
  <table><thead><tr><th>Zeit</th><th>Tag</th><th>Kriterium</th><th>Status</th><th>Grund</th></tr></thead>
  <tbody id="wd-acceptance-checks"></tbody></table>
  <h3 style="font-size:.85rem;color:#94a3b8;margin:1rem 0 .5rem;text-transform:uppercase">Runs <span style="font-size:.7rem;color:#64748b;text-transform:none;font-weight:400" id="wd-runs-trend"></span></h3>
  <table><thead><tr><th>#</th><th>Start</th><th>Ende</th><th>Score</th><th>Stages</th><th>Status</th><th>PR</th></tr></thead>
  <tbody id="wd-runs"></tbody></table>
  <h3 style="font-size:.85rem;color:#94a3b8;margin:1rem 0 .5rem;text-transform:uppercase">Audit Trail</h3>
  <table><thead><tr><th>Zeit</th><th>Level</th><th>Stage</th><th>Event</th><th>Message</th><th>OWASP</th><th>AI Act</th></tr></thead>
  <tbody id="wd-events"></tbody></table>
 </div>
 <div class="section"><h2>Branches</h2>
  <table><thead><tr><th>Branch</th><th>Issue</th><th>Status</th></tr></thead>
  <tbody id="w-branches"></tbody></table>
 </div>
</div>

<!-- TAB: PROBLEMS (#429) -->
<div class="tab-content" id="tab-problems">
 <div class="grid" style="grid-template-columns:repeat(3,1fr);gap:.5rem;margin-bottom:.75rem">
  <div class="card"><h3>Errors</h3><div class="val err" id="prob-count-error">-</div></div>
  <div class="card"><h3>Warnings</h3><div class="val warn" id="prob-count-warn">-</div></div>
  <div class="card"><h3>Historisch / ungültig</h3><div class="val" id="prob-count-historical">-</div></div>
 </div>
 <div class="filter-bar">
  <select id="prob-level"><option value="">Alle Level</option><option value="error">Error</option><option value="warn">Warn</option></select>
  <select id="prob-cat"><option value="">Alle Kategorien</option></select>
  <input type="text" id="prob-issue" inputmode="numeric" placeholder="Issue, z.B. 429">
  <label style="font-size:.8rem;color:#94a3b8;display:flex;align-items:center;gap:.3rem"><input type="checkbox" id="prob-history"> Historische/ungültige anzeigen</label>
  <label style="font-size:.8rem;color:#94a3b8;display:flex;align-items:center;gap:.3rem"><input type="checkbox" id="prob-debug"> Debug-Details</label>
 </div>
 <div class="section" style="max-height:600px;overflow:auto">
  <table><thead><tr><th>Zuletzt</th><th>Status</th><th>Level</th><th>Typ</th><th>Issue</th><th>Problem / Ursache / Auswirkung</th><th>Nächste Schritte</th><th>Datei</th><th class="prob-debug-col" style="display:none">Details</th></tr></thead>
  <tbody id="prob-body"></tbody></table>
 </div>
</div>

<!-- TAB: LOGS -->
<div class="tab-content" id="tab-logs">
 <div class="grid" style="grid-template-columns:repeat(3,1fr);gap:.5rem;margin-bottom:.75rem">
  <div class="card"><h3>Errors</h3><div class="val err" id="log-count-error">-</div></div>
  <div class="card"><h3>Warnings</h3><div class="val warn" id="log-count-warn">-</div></div>
  <div class="card"><h3>Info</h3><div class="val ok" id="log-count-info">-</div></div>
 </div>
 <div class="filter-bar">
  <select id="log-cat"><option value="">Alle Kategorien</option></select>
  <select id="log-level"><option value="">Alle Level</option><option value="error">Error</option><option value="warn">Warn</option><option value="info">Info</option><option value="debug">Debug</option></select>
  <input type="text" id="log-search" placeholder="Textsuche...">
 </div>
 <div class="section" style="max-height:500px;overflow-y:auto">
  <table><thead><tr><th style="width:1.5rem"></th><th>Zeit</th><th>Level</th><th>Category</th><th>Event</th><th>Message</th><th>Issue</th></tr></thead>
  <tbody id="log-body"></tbody></table>
 </div>
</div>

<!-- TAB: SECURITY -->
<div class="tab-content" id="tab-security">
 <div id="sec-tamper-banner" style="display:none;background:#dc2626;color:#fff;border-radius:8px;padding:1rem;margin-bottom:1rem"></div>
 <div class="grid">
  <div class="card"><h3>Total Events</h3><div class="val" id="sec-total">-</div></div>
  <div class="card"><h3>Classified</h3><div class="val" id="sec-classified">-</div></div>
  <div class="card"><h3>Active Risks</h3><div class="val" id="sec-risks">-</div></div>
 </div>
 <div class="section"><h2>Branch-Protection <span style="font-size:.7rem;color:#64748b;font-weight:400">(Default-Branch auf SCM)</span></h2>
  <div id="sec-branch-protection"><div class="empty">Laden...</div></div>
 </div>
 <div class="section"><h2>OWASP Agentic AI Top 10 <span style="font-size:.7rem;color:#64748b;font-weight:400">(Zeile klicken fuer Recent-Events)</span></h2>
  <table><thead><tr><th>ID</th><th>Category</th><th>Events</th><th>Last</th></tr></thead>
  <tbody id="sec-owasp"></tbody></table>
  <div id="sec-owasp-recent" style="margin-top:.75rem"></div>
 </div>
 <div class="section"><h2>Schranken-Protokoll (letzte 30)</h2>
  <table><thead><tr><th>Zeit</th><th>Issue</th><th>Step</th><th>Gate/Event</th><th>Action</th><th>OWASP</th><th>Detail</th></tr></thead>
  <tbody id="sec-barrier"></tbody></table>
 </div>
 <div class="section"><h2>OpenTelemetry gen_ai.* Calls (letzte 30)</h2>
  <table><thead><tr><th>Zeit</th><th>system</th><th>model</th><th>input</th><th>output</th><th>total</th><th>duration_ms</th><th>finish</th><th>task</th></tr></thead>
  <tbody id="sec-otel"></tbody></table>
 </div>
 <div class="section"><h2>Sicherheits- und Integritätsereignisse</h2>
  <table><thead><tr><th>Zeit</th><th>Klasse</th><th>Quelle / Komponente</th><th>Detail / Auswirkung / Maßnahme</th><th>Run / Issue</th></tr></thead>
  <tbody id="sec-tamper"></tbody></table>
 </div>
</div>

<!-- TAB: COMPLIANCE (#252) -->
<div class="tab-content" id="tab-compliance">
 <div class="section"><h2>OWASP Top-10 Agentic AI</h2>
  <p style="font-size:.8rem;color:#94a3b8;margin-bottom:.5rem">Risiko-Kategorien wie sie im Audit-Trail (Spalte OWASP) und Workflow-Detail erscheinen. <a href="https://owasp.org/www-project-agentic-ai-top-10/" target="_blank" style="color:#38bdf8">OWASP-Referenz</a></p>
  <table><thead><tr><th>ID</th><th>Name</th><th>Key</th><th>Beschreibung</th></tr></thead>
  <tbody id="comp-owasp"></tbody></table>
 </div>
 <div class="section"><h2>EU AI Act — Relevante Artikel</h2>
  <p style="font-size:.8rem;color:#94a3b8;margin-bottom:.5rem">Artikel-Nummern aus VO (EU) 2024/1689 wie sie im Audit-Trail (Spalte AI Act) erscheinen. Ob ein Artikel <span class="badge badge-ok">Pflicht</span> oder <span class="badge badge-warn">freiwillig</span> ist, haengt von der Risikoklasse des ueberwachten Deployments ab — nicht von SAMUEL selbst.</p>
  <div id="aiact-riskclass" style="font-size:.8rem;margin-bottom:.5rem;color:#cbd5e1"></div>
  <table><thead><tr><th>Artikel</th><th>Verpflichtung</th><th>Beschreibung</th></tr></thead>
  <tbody id="comp-aiact"></tbody></table>
 </div>
 <div class="section"><h2>LLM-Code-Kennzeichnung (Art. 50)</h2>
  <p style="font-size:.8rem;color:#94a3b8;margin-bottom:.5rem">Steuert die <strong>externe</strong> Sichtbarkeit: Inline-Marker im generierten Code (<code>llm: &lt;modell&gt; &lt;datum&gt;</code>) und der von GitHub gerenderte <code>Co-Authored-By</code>-Trailer. Die <strong>Audit-Ebene</strong> (<code>AI-Generated-By</code>-Trailer + <code>LLMCallCompleted</code>-Events) bleibt unabhaengig davon immer aktiv.</p>
  <div id="aiact-attribution" style="font-size:.8rem;color:#cbd5e1"></div>
 </div>
</div>

<!-- TAB: SETUP (#402) -->
<div class="tab-content" id="tab-setup">
 <div class="section">
  <h2>Ersteinrichtung</h2>
  <p class="setup-note">Geheimnisse werden nie wieder ausgelesen oder angezeigt. Leere Geheimnisfelder behalten vorhandene Werte. Ohne bestehenden API-Key ist dieser Schreibweg ausschliesslich ueber localhost erreichbar.</p>
  <div id="setup-status" class="warn-item">Status wird geladen...</div>
 </div>
 <div class="section"><h2>SCM und Zielprojekt</h2>
  <div class="setup-form">
   <label>Provider<select id="setup-scm-provider"><option value="gitea">Gitea</option><option value="github">GitHub</option></select></label>
   <label>Server/API-URL<input id="setup-scm-url" type="url" placeholder="https://gitea.example.org"></label>
   <label>Repository<input id="setup-scm-repo" placeholder="owner/repository"></label>
   <label>Erwarteter Required Check<input id="setup-scm-required-status-context" placeholder="CI / lint-and-test (pull_request)"></label>
   <label>Benutzer<input id="setup-scm-user" autocomplete="username"></label>
   <label>Bot-Benutzer<input id="setup-scm-bot-user"></label>
   <label>SCM-Token<input id="setup-scm-token" type="password" autocomplete="new-password" placeholder="vorhandener Wert bleibt erhalten"></label>
   <label>Zielprojekt (optional)<input id="setup-project-root" placeholder="/pfad/zum/projekt"></label>
   <label>Dashboard-Port<input id="setup-dashboard-port" type="number" min="1" max="65535" value="7777"></label>
  </div>
 </div>
 <div class="section"><h2>LLM</h2>
  <div class="setup-form">
   <label>Provider<select id="setup-llm-provider"><option value="deepseek">DeepSeek</option><option value="gemini">Gemini</option><option value="openai">OpenAI</option><option value="claude">Claude</option><option value="openrouter">OpenRouter</option><option value="ollama">Ollama</option><option value="lmstudio">LM Studio</option><option value="manual">Manuell</option></select></label>
   <label>Modell (optional)<input id="setup-llm-model"></label>
   <label>Lokale Base-URL<input id="setup-llm-base-url" type="url" placeholder="http://localhost:11434"></label>
   <label>API-Key<input id="setup-llm-api-key" type="password" autocomplete="new-password" placeholder="vorhandener Wert bleibt erhalten"></label>
  </div>
 </div>
 <div class="section"><h2>Sicherheit und Speichern</h2>
  <div class="setup-form"><label>Eigener Dashboard-API-Key (optional)<input id="setup-dashboard-api-key" type="password" autocomplete="new-password" placeholder="sonst sicher erzeugt"></label></div>
  <label style="display:flex;align-items:center;gap:.4rem;font-size:.8rem;margin:.75rem 0"><input id="setup-allow-unverified" type="checkbox"> Trotz fehlgeschlagener Verbindungstests speichern</label>
  <button id="setup-save" onclick="saveSetupWizard()" style="background:#0ea5e9;color:#0f172a;border:none;padding:.6rem 1rem;border-radius:4px;font-weight:600;cursor:pointer">Pruefen und speichern</button>
  <div id="setup-result" style="margin-top:.75rem;font-size:.82rem"></div>
  <div id="setup-new-key" class="warn-item" style="display:none;margin-top:.75rem"></div>
 </div>
</div>

<!-- TAB: SETTINGS -->
<div class="tab-content" id="tab-settings">
 <div class="section"><h2>Operator-Konfiguration</h2><div id="set-config-mode"><div class="empty">Laden...</div></div></div>
 <div class="section"><h2>Documentation Extension</h2><div id="set-documentation-extension"><div class="empty">Laden...</div></div></div>
 <div class="section"><h2>Feature Flags</h2><div id="set-flags"><div class="empty">Laden...</div></div></div>
 <div class="section"><h2>Setup</h2>
  <button id="btn-sync-labels" onclick="syncLabels()" style="background:#0ea5e9;color:#0f172a;border:none;padding:.5rem 1rem;border-radius:4px;font-size:.85rem;cursor:pointer;font-weight:600">Labels auf SCM synchronisieren</button>
  <div id="labels-result" style="margin-top:.75rem;font-size:.8rem;color:#94a3b8"></div>
 </div>
 <div class="section"><h2>Dead-Letter-Queue</h2>
  <p style="font-size:.8rem;color:#94a3b8;margin-bottom:.5rem">Events, deren Handler abgestuerzt sind (#334). Re-Publish via CLI <code>samuel dlq replay &lt;id&gt;</code>.</p>
  <div id="set-dlq"><div class="empty">Laden...</div></div>
 </div>
 <div class="section"><h2>LLM Default &amp; Fallback</h2><div id="set-llm-global"><div class="empty">Laden...</div></div></div>
 <div class="section"><h2>LLM Task Configuration</h2><div id="set-llm-config"><div class="empty">Laden...</div></div></div>
 <div class="section"><h2>Identitäten und Sitzungen</h2><div id="set-identity"><div class="empty">Laden...</div></div></div>
 <div class="section"><h2>API Keys</h2><div id="set-api-keys"><div class="empty">Laden...</div></div></div>
 <div class="section" id="set-warnings-section" style="display:none"><h2>Transfer-Warnungen (DSGVO)</h2><div id="set-warnings"></div></div>
</div>

<!-- TAB: SELF-CHECK -->
<div class="tab-content" id="tab-selfcheck">
 <div class="grid">
  <div class="card"><h3>Modus</h3><div class="val" id="sc-mode">-</div></div>
  <div class="card"><h3>Technische Gesundheit</h3><div class="val" id="sc-healthy">-</div></div>
  <div class="card"><h3>Betriebsbereitschaft</h3><div class="val" id="sc-readiness">-</div></div>
  <div class="card"><h3>Qualification</h3><div class="val" id="sc-qualification">-</div></div>
 </div>
 <div class="section"><h2>Checks</h2>
  <table><thead><tr><th>Name</th><th>Status</th><th>Zeit</th><th>Detail</th></tr></thead>
  <tbody id="sc-body"></tbody></table>
 </div>
</div>

<script>
let currentTab=sessionStorage.getItem('tab')||'status';
const REFRESH_INTERVAL=10;
let cd=REFRESH_INTERVAL;
let autoRefresh=(sessionStorage.getItem('autoRefresh')||'on')==='on';
let allLogs=[];
let allProblems=[];
function fmtTime(value){
 if(!value)return '-';
 const raw=String(value);
 if(!/^\\d{4}-\\d{2}-\\d{2}[T ]/.test(raw))return raw;
 if(!/(Z|[+-]\\d{2}:\\d{2})$/.test(raw))return raw+' [Zeitzone unbekannt]';
 const date=new Date(raw.replace(' ','T'));
 if(!Number.isFinite(date.getTime()))return raw;
 const zone=document.getElementById('last-refresh')?.dataset?.timezone||'UTC';
 const options={year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23',timeZoneName:'shortOffset'};
 try{return new Intl.DateTimeFormat('de-DE',{...options,timeZone:zone}).format(date)+' ['+zone+']';}
 catch(e){return new Intl.DateTimeFormat('de-DE',{...options,timeZone:'UTC'}).format(date)+' [UTC; konfigurierte Zeitzone nicht verfügbar]';}
}
const ts=()=>fmtTime(new Date().toISOString());
const esc=s=>{const d=document.createElement('div');d.textContent=s;return d.innerHTML};
const fmt=n=>typeof n==='number'?n.toLocaleString('de-DE'):(n||'-');

function applyTheme(theme){
 const normalized=theme==='light'?'light':'dark';
 document.documentElement.dataset.theme=normalized;
 try{localStorage.setItem('samuel-theme',normalized);}catch(e){}
 const button=document.getElementById('theme-toggle');
 if(button){button.textContent=normalized==='light'?'Dunkel':'Hell';button.setAttribute('aria-pressed',normalized==='light'?'true':'false');}
}
function toggleTheme(){applyTheme(document.documentElement.dataset.theme==='light'?'dark':'light');}

// #359: Compliance-Legende lazy-cachen, damit Click-Expand auf OWASP-/AI-Act-
// Codes im Audit-Trail und Schranken-Protokoll ohne Roundtrip pro Klick laeuft.
let complianceCache=null;
async function ensureLegend(){
 if(complianceCache)return complianceCache;
 try{
  const r=await apiFetch('/api/v1/dashboard/compliance/legend');
  const j=await r.json();const d=j.data||j;
  complianceCache={owasp:d.owasp||[],ai_act:d.ai_act||[],ai_act_risk_class:d.ai_act_risk_class||''};
 }catch(e){complianceCache={owasp:[],ai_act:[],ai_act_risk_class:''};}
 return complianceCache;
}
// Match by full OWASP-key (uncontrolled_behavior), or by short ID (A05),
// or by versioned ID (A05:2021). Returns "" when nothing matches.
function owaspDesc(v){
 if(!v||!complianceCache)return '';
 const key=String(v).trim();
 const idShort=key.split(':')[0];
 for(const r of complianceCache.owasp){
  if(r.key===key||r.id===key||r.id===idShort)return r.description||r.name||'';
 }
 return '';
}
function aiActDesc(v){
 if(!v||!complianceCache)return '';
 const key=String(v).trim();
 for(const r of complianceCache.ai_act){
  if(r.article===key||('Art. '+r.article)===key)return r.description||r.title||'';
 }
 return '';
}
// #371: obligation-Lookup pro Artikel — required (Limited-Risk-Pflicht) vs
// voluntary (freiwillig angewandter High-Risk-Standard).
function aiActObligation(v){
 if(!v||!complianceCache)return '';
 const key=String(v).trim();
 for(const r of complianceCache.ai_act){
  if(r.article===key||('Art. '+r.article)===key)return r.obligation||'';
 }
 return '';
}
// #371: obligation -> Badge-HTML. Gruen = gesetzliche Pflicht, gelb = freiwillig.
function obligationBadge(o){
 const v=String(o||'').trim();
 if(v==='required')return '<span class="badge badge-ok">Pflicht</span>';
 if(v==='voluntary')return '<span class="badge badge-warn">freiwillig</span>';
 return '';
}
// #373: Deployment-Risikoklasse -> lesbares Label fuer die Compliance-Tab-Anzeige.
function riskClassLabel(rc){
 const v=String(rc||'').trim();
 if(v==='high_risk')return 'High Risk (Annex III)';
 if(v==='limited_risk')return 'Limited Risk';
 if(v==='minimal_risk')return 'Minimal Risk';
 return v||'unbekannt';
}

function apiHeaders(){
 if(authMode==='local_identity')return {};
 const k=sessionStorage.getItem('apiKey')||'';
 return k?{'X-API-Key':k}:{};
}
function cookieValue(name){
 const prefix=name+'=';
 for(const item of document.cookie.split(';')){const value=item.trim();if(value.startsWith(prefix))return decodeURIComponent(value.slice(prefix.length));}
 return '';
}
let authMode='unknown';
let currentActor=null;
let authModePromise=null;
async function ensureAuthMode(){
 if(authMode!=='unknown')return authMode;
 if(authModePromise)return authModePromise;
 authModePromise=fetch('/api/v1/auth/mode').then(async response=>{
  if(!response.ok)throw new Error('access mode unavailable');
  const data=await response.json();authMode=data.access_mode||'unknown';
  const local=authMode==='local_identity';
  const user=document.getElementById('auth-user'),userLabel=document.getElementById('auth-user-label');
  const keyLabel=document.getElementById('auth-key-label'),help=document.getElementById('auth-help');
  if(user)user.style.display=local?'block':'none';if(userLabel)userLabel.style.display=local?'block':'none';
  if(keyLabel)keyLabel.textContent=local?'Passwort':'SAMUEL_API_KEY';
  if(help)help.textContent=local?'Mit einer lokalen S.A.M.U.E.L.-Identität anmelden.':'Der API-Key gilt nur für diesen Browser-Tab und wird beim Schließen verworfen.';
  return authMode;
 }).finally(()=>{authModePromise=null;});
 return authModePromise;
}
function updateActor(actor){
 currentActor=actor||null;
 const button=document.getElementById('auth-logout');
 if(button)button.style.display=authMode==='local_identity'&&currentActor?'inline-block':'none';
}
let authPromptPromise=null;
let authDialogResolve=null;
async function validateApiKey(key){
 const mode=await ensureAuthMode();
 const candidate=String(key||'');
 if(!candidate)return false;
 if(mode==='local_identity'){
  const username=String((document.getElementById('auth-user')||{}).value||'').trim();
  if(!username)return false;
  const res=await fetch('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:username,password:candidate})});
  if(res.ok){const data=await res.json();updateActor(data.actor);showToast('Anmeldung erfolgreich','ok');return true;}
  updateActor(null);showToast('Anmeldung fehlgeschlagen','err');return false;
 }
 const normalized=candidate.trim();
 const res=await fetch('/api/v1/auth/check',{headers:{'X-API-Key':normalized}});
 if(res.ok){
  sessionStorage.setItem('apiKey',normalized);
  showToast('API-Key akzeptiert','ok');
  return true;
 }
 sessionStorage.removeItem('apiKey');
 showToast('API-Key ungueltig oder nicht mehr gueltig','err');
 return false;
}
function closeApiKeyDialog(result){
 const overlay=document.getElementById('auth-overlay');
 const input=document.getElementById('auth-key');
 if(overlay)overlay.style.display='none';
 if(input)input.value='';
 const resolve=authDialogResolve;authDialogResolve=null;
 if(resolve)resolve(result);
}
async function submitApiKey(){
 const input=document.getElementById('auth-key');
 const feedback=document.getElementById('auth-feedback');
 const button=document.getElementById('auth-submit');
 const candidate=input?input.value:'';
 if(!candidate){if(feedback){feedback.textContent='Bitte das Zugangsdatenfeld ausfüllen.';feedback.style.color='#fbbf24';}return;}
 if(button)button.disabled=true;
 if(feedback){feedback.textContent='Zugangsdaten werden geprüft …';feedback.style.color='var(--muted)';}
 try{
  if(await validateApiKey(candidate)){if(feedback)feedback.textContent='Anmeldung erfolgreich.';closeApiKeyDialog(true);}
  else if(feedback){feedback.textContent='Zugangsdaten sind falsch oder nicht mehr gültig.';feedback.style.color='#f87171';}
 }catch(err){
  sessionStorage.removeItem('apiKey');
  if(feedback){feedback.textContent='Prüfung nicht möglich: '+String(err);feedback.style.color='#f87171';}
 }finally{if(button)button.disabled=false;}
}
function cancelApiKey(){closeApiKeyDialog(false);}
function requestApiKey(){
 if(authPromptPromise)return authPromptPromise;
 authPromptPromise=ensureAuthMode().then(()=>new Promise(resolve=>{
  authDialogResolve=resolve;
  const overlay=document.getElementById('auth-overlay');
  const feedback=document.getElementById('auth-feedback');
  const input=document.getElementById('auth-key');
  if(feedback){feedback.textContent='';feedback.style.color='var(--muted)';}
  if(overlay)overlay.style.display='flex';
  const user=document.getElementById('auth-user');
  if(authMode==='local_identity'&&user)setTimeout(()=>user.focus(),0);else if(input)setTimeout(()=>input.focus(),0);
 })).finally(()=>{authPromptPromise=null;});
 return authPromptPromise;
}
async function apiFetch(url,opts){
 opts=opts||{};
 await ensureAuthMode();
 const headers=Object.assign({},opts.headers||{},apiHeaders());
 if(authMode==='local_identity'&&String(opts.method||'GET').toUpperCase()!=='GET')headers['X-CSRF-Token']=cookieValue('samuel_csrf');
 let res=await fetch(url,Object.assign({},opts,{headers:headers}));
 // #422: Den Key einmal zentral und sofort validieren. Parallele 401-Requests
 // teilen dieselbe Anmeldung und fahren nach Erfolg ohne Refresh-Zyklus fort.
 if(res.status===401){
  sessionStorage.removeItem('apiKey');
  updateActor(null);
  if(await requestApiKey()){
   const retryHeaders=Object.assign({},opts.headers||{},apiHeaders());
   if(authMode==='local_identity'&&String(opts.method||'GET').toUpperCase()!=='GET')retryHeaders['X-CSRF-Token']=cookieValue('samuel_csrf');
   res=await fetch(url,Object.assign({},opts,{headers:retryHeaders}));
  }
 }
 return res;
}
async function logoutIdentity(){
 if(authMode!=='local_identity')return;
 const response=await apiFetch('/api/v1/auth/logout',{method:'POST'});
 if(response.ok){updateActor(null);showToast('Abgemeldet','ok');await requestApiKey();}
}
function showToast(msg,kind){
 const el=document.getElementById('toast');
 el.textContent=msg;
 const bg=kind==='err'?'#7f1d1d':(kind==='warn'?'#78350f':'#065f46');
 el.style.background=bg;el.style.color='#e2e8f0';el.style.display='block';
 setTimeout(()=>{el.style.display='none';},5000);
}

function showTab(name){
 currentTab=name;sessionStorage.setItem('tab',name);
 document.querySelectorAll('.tab-content').forEach(t=>t.style.display='none');
 const el=document.getElementById('tab-'+name);if(el)el.style.display='block';
 document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));
 if(typeof event!=='undefined'&&event&&event.target)event.target.classList.add('active');
 else{const btns=document.querySelectorAll('.tab');btns.forEach(b=>{if(b.getAttribute('onclick')==="showTab('"+name+"')")b.classList.add('active');});}
 loadTabData(name);
 cd=REFRESH_INTERVAL;
}

function toggleAutoRefresh(){
 autoRefresh=!autoRefresh;
 sessionStorage.setItem('autoRefresh',autoRefresh?'on':'off');
 document.getElementById('auto-refresh-btn').textContent='auto-refresh: '+(autoRefresh?'on':'off');
 cd=REFRESH_INTERVAL;
}

async function loadTabData(tab){
 try{
  if(tab==='status')await loadStatus();
  else if(tab==='llm')await loadLLM();
  else if(tab==='quality')await loadQuality();
  else if(tab==='activity')await loadActivity();
  else if(tab==='workflow')await loadWorkflow();
  else if(tab==='problems')await loadProblems();
  else if(tab==='logs')await loadLogs();
  else if(tab==='security')await loadSecurity();
  else if(tab==='compliance')await loadCompliance();
  else if(tab==='setup')await loadSetupWizard();
  else if(tab==='settings')await loadSettings();
  else if(tab==='selfcheck')await loadSelfCheck();
  document.getElementById('last-refresh').textContent=ts();
 }catch(e){console.error('Tab load failed:',tab,e)}
}

let setupLoaded=false;
let setupWritable=false;
function setupValue(id){return document.getElementById(id).value.trim()}
async function loadSetupWizard(){
 const r=await apiFetch('/api/v1/setup/status');
 const status=document.getElementById('setup-status');
 if(r.status===403){status.textContent='Einrichtung ohne bestehenden API-Key ist nur ueber localhost erlaubt.';return}
 if(r.status===401){status.textContent='Zur Aenderung ist der bestehende Dashboard-API-Key erforderlich.';return}
 if(!r.ok){status.textContent='Setup-Status konnte nicht geladen werden.';return}
 const d=await r.json(),v=d.values||{},configuration=d.configuration||{};
 setupWritable=configuration.writable===true;
 status.textContent=d.first_run?'Ersteinrichtung ist noch nicht abgeschlossen.':'Grundkonfiguration ist vorhanden; leere Geheimnisfelder bleiben unveraendert.';
 const requiredSource=v.scm_required_status_context_source==='configured'?'konfiguriert':(v.scm_required_status_context_source==='shipped_default'?'ausgelieferter Default':'ungueltig');
 status.textContent+=' Required-Check-Soll: '+(v.scm_required_status_context||'-')+' (Quelle: '+requiredSource+').';
 status.textContent+=setupWritable?' Schreibmodus aktiv; gespeicherte Änderungen benötigen einen Neustart.':' Konfiguration eingefroren: Produktionsdienst stoppen; mit derselben Konfiguration das lokale Dashboard ausdrücklich mit --configuration-mode setup starten; prüfen und speichern; Setup beenden; Produktionsruntime neu erzeugen; gespeicherte/wirksame Werte und Produktions-Freeze prüfen. Details: Installationsanleitung Abschnitt 4.3.';
 status.className=d.first_run?'warn-item':'section';
 document.getElementById('setup-save').disabled=!setupWritable;
 if(!setupLoaded){
  const fields={
   'setup-scm-provider':v.scm_provider,'setup-scm-url':v.scm_url,'setup-scm-repo':v.scm_repo,
   'setup-scm-required-status-context':v.scm_required_status_context,
   'setup-scm-user':v.scm_user,'setup-scm-bot-user':v.scm_bot_user,
   'setup-project-root':v.project_root,'setup-dashboard-port':v.dashboard_port,
   'setup-llm-provider':v.llm_provider,'setup-llm-model':v.llm_model,'setup-llm-base-url':v.llm_base_url
  };
  Object.entries(fields).forEach(([id,value])=>{if(value!==undefined&&value!==null)document.getElementById(id).value=value});
  setupLoaded=true;
 }
}
async function saveSetupWizard(){
 const button=document.getElementById('setup-save'),out=document.getElementById('setup-result'),keyBox=document.getElementById('setup-new-key');
 if(!setupWritable){out.textContent='Nicht gespeichert: Konfiguration ist im Produktionsmodus eingefroren.';return;}
 button.disabled=true;out.textContent='Verbindungen werden geprueft...';keyBox.style.display='none';
 const payload={
  scm_provider:setupValue('setup-scm-provider'),scm_url:setupValue('setup-scm-url'),scm_repo:setupValue('setup-scm-repo'),
  scm_required_status_context:setupValue('setup-scm-required-status-context'),
  scm_user:setupValue('setup-scm-user'),scm_bot_user:setupValue('setup-scm-bot-user'),scm_token:setupValue('setup-scm-token'),
  project_root:setupValue('setup-project-root'),dashboard_port:setupValue('setup-dashboard-port'),
  llm_provider:setupValue('setup-llm-provider'),llm_model:setupValue('setup-llm-model'),llm_base_url:setupValue('setup-llm-base-url'),
  llm_api_key:setupValue('setup-llm-api-key'),dashboard_api_key:setupValue('setup-dashboard-api-key'),
  allow_unverified:document.getElementById('setup-allow-unverified').checked
 };
 try{
  const r=await apiFetch('/api/v1/setup/configure',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const d=await r.json();
  if(!r.ok){out.textContent='Nicht gespeichert: '+(d.errors||[d.error||'unbekannter Fehler']).join(' | ');showToast('Setup nicht gespeichert','err');return}
  const effective=d.api_key||payload.dashboard_api_key;
  if(effective&&authMode==='legacy_api_key')sessionStorage.setItem('apiKey',effective);
  if(d.api_key){keyBox.textContent='Neuer Dashboard-API-Key (nur jetzt sichtbar): '+d.api_key+' — bitte sicher speichern.';keyBox.style.display='block'}
  const probes=Object.entries(d.probes||{}).map(([name,p])=>name+': '+(p.valid?'OK':'FEHLER')+' ('+(p.detail||'-')+')').join(' · ');
  out.textContent='Gespeichert. Neustart erforderlich, damit SCM/LLM-Adapter die neue Konfiguration laden.'+(probes?' '+probes:'');
  ['setup-scm-token','setup-llm-api-key','setup-dashboard-api-key'].forEach(id=>document.getElementById(id).value='');
  showToast('Setup sicher gespeichert','ok');await loadSetupWizard();
 }catch(e){out.textContent='Netzwerkfehler: '+e;showToast('Setup fehlgeschlagen','err')}
 finally{button.disabled=!setupWritable}
}

async function checkFirstRun(){
 try{
  const r=await apiFetch('/api/v1/setup/status');
  if(!r.ok)return;
  const d=await r.json();setupWritable=(d.configuration||{}).writable===true;if(d.first_run&&currentTab!=='setup')showTab('setup');
 }catch(e){}
}

async function loadStatus(){
 const[sr,hr]=await Promise.all([
  apiFetch('/api/v1/dashboard/status').then(r=>r.json()),
  apiFetch('/api/v1/dashboard/health').then(r=>r.json())
 ]);
 const hd=hr.data||hr;
 const build=sr.build||{};
 const productVersion=document.getElementById('product-version');
 if(productVersion)productVersion.textContent=build.product_version||'0+unknown';
 const buildRevision=document.getElementById('build-revision');
 if(buildRevision){
  const revision=build.revision||'';
  buildRevision.textContent=revision?' · '+revision.slice(0,12)+(build.dirty?' dirty':''):'';
  buildRevision.title=revision?('Build-Revision: '+revision+(build.dirty?' (dirty)':'')):'Build-Revision nicht verfügbar';
 }
 const modeEl=document.getElementById('s-mode');
 modeEl.textContent=(sr.mode||'?')+(sr.self_mode?' (self)':'');
 modeEl.className='val '+(sr.self_mode?'warn':'');
 const scm=document.getElementById('s-scm');
 scm.textContent=sr.scm_connected?'Verbunden':'Getrennt';
 scm.className='val '+(sr.scm_connected?'ok':'warn');
 const healthy=hd.healthy;
 const hEl=document.getElementById('s-health');
 hEl.textContent=healthy?'OK':'Fehler';hEl.className='val '+(healthy?'ok':'err');
 const checks=hd.checks||{};
 const llmOk=checks.llm;
 const lEl=document.getElementById('s-llm');
 if(llmOk===undefined){lEl.textContent='N/A';lEl.className='val warn'}
 else{lEl.textContent=llmOk?'OK':'Fehler';lEl.className='val '+(llmOk?'ok':'err')}
 // #277: Recovered Issues — Self-Healing-Indikator
 const recEl=document.getElementById('s-recovered');
 if(recEl){const rc=sr.recovered_count||0;recEl.textContent=fmt(rc);recEl.className='val '+(rc>0?'ok':'');}
 const hDiv=document.getElementById('s-health-details');hDiv.innerHTML='';
 for(const[k,v]of Object.entries(checks)){
  hDiv.innerHTML+='<div class="health-row"><span><span class="dot '+(v?'g':'r')+'"></span>'+esc(k)+'</span><span>'+(v?'OK':'FAIL')+'</span></div>';
 }
 const retention=hd.retention||{};const rDiv=document.getElementById('s-retention');rDiv.innerHTML='';
 if(retention.status!=='available'){
  rDiv.innerHTML='<div class="health-row"><span>Status</span><span class="warn">Nicht geprüft</span></div>';
 }else{
  const stopped=retention.retention_emergency_stop===true;
  rDiv.innerHTML+='<div class="health-row"><span>Not-Aus</span><span class="'+(stopped?'warn':'ok')+'">'+(stopped?'Aktiv':'Freigegeben')+'</span></div>';
  rDiv.innerHTML+='<div class="health-row"><span>Pending Review</span><span>'+fmt(retention.pending_review_count||0)+'</span></div>';
  (retention.categories||[]).forEach(c=>{
   const binding=[c.category_digest,c.profile_role_digest,c.evidence_digest].filter(Boolean).join(' · ');
   const grant=[c.grant_cutoff_utc,c.activated_at].filter(Boolean).map(fmtTime).join(' / ');
   rDiv.innerHTML+='<div class="health-row"><span>'+esc(c.category)+' · '+esc(c.effective_mode)+'</span><span title="'+esc(binding)+'">'+esc(binding)+(grant?' · '+esc(grant):'')+'</span></div>';
  });
  const last=retention.last_execution;
  rDiv.innerHTML+='<div class="health-row"><span>Letzte Wirkung</span><span>'+(last?(esc(last.category)+' · '+fmt(last.deleted_count)+' · '+esc(fmtTime(last.executed_at))+' · '+esc(last.plan_digest)):'Keine')+'</span></div>';
 }
 const m=sr.metrics||{};
 const counts=m.counts||{},errors=m.errors||{},tms=m.total_ms||{};
 const keys=new Set([...Object.keys(counts),...Object.keys(errors)]);
 const tb=document.getElementById('s-activity');tb.innerHTML='';
 [...keys].forEach(k=>{const c=counts[k]||0,e=errors[k]||0,a=c?(tms[k]||0)/c:0;
  tb.innerHTML+='<tr><td>'+esc(k)+'</td><td>'+c+'</td><td class="'+(e?'err':'')+'">'+e+'</td><td>'+a.toFixed(1)+'</td></tr>';
 });
 if(!keys.size)tb.innerHTML='<tr><td colspan="4" class="empty">Keine Events</td></tr>';
 const tilesDiv=document.getElementById('s-tiles');tilesDiv.innerHTML='';
 (sr.tiles||[]).forEach(t=>{
  const cls=t.kind==='ok'?'ok':t.kind==='warn'?'warn':t.kind==='err'?'err':'';
  tilesDiv.innerHTML+='<div class="card"><h3>'+esc(t.label||'-')+'</h3><div class="val '+cls+'" style="font-size:1rem">'+esc(String(t.value||'-'))+'</div><div style="font-size:.7rem;color:#94a3b8;margin-top:.25rem">'+esc(t.detail||'')+'</div></div>';
 });
 const resume=sr.resume||{};
 const resumeState=resume.enabled?'aktiv':(resume.reconcile_required?'Reconcile':'deaktiviert');
 const resumeClass=resume.reconcile_required||Number(resume.blocked||0)>0?'err':Number(resume.pending||0)>0?'warn':resume.enabled?'ok':'';
 tilesDiv.innerHTML+='<div class="card"><h3>Restart-Resume</h3><div class="val '+resumeClass+'" style="font-size:1rem">'+esc(resumeState)+'</div><div style="font-size:.7rem;color:#94a3b8;margin-top:.25rem">pending '+fmt(resume.pending||0)+' · blocked '+fmt(resume.blocked||0)+'</div></div>';
 const sh=document.getElementById('s-score-history');sh.innerHTML='';
 const hist=sr.score_history||[];
 if(hist.length){hist.forEach(h=>{
  const passive=h.non_binding===true;
  const cls=passive?'warn':(h.passed?'ok':'err');
  const status=passive?'NICHT BINDEND':(h.passed?'LEGACY PASS':'LEGACY FAIL');
  sh.innerHTML+='<tr><td style="font-size:.75rem">'+esc(fmtTime(h.timestamp||'-'))+'</td><td>'+(h.issue?'#'+esc(String(h.issue)):'-')+'</td><td>'+(h.score!=null?String(h.score):'-')+'</td><td>'+(h.baseline!=null?String(h.baseline):'-')+'</td><td class="'+cls+'">'+status+'</td><td style="font-size:.75rem">'+esc(h.reason||h.label||'-')+'</td></tr>';
 });}else{sh.innerHTML='<tr><td colspan="6" class="empty">Keine Eval-Events</td></tr>';}
 const an=document.getElementById('s-anomalies');an.innerHTML='';
 const anoms=sr.anomalies||[];
 if(anoms.length){anoms.forEach(a=>{
  const cls=a.level==='error'?'err':'warn';
  an.innerHTML+='<tr><td style="font-size:.75rem">'+esc(fmtTime(a.timestamp||'-'))+'</td><td class="'+cls+'">'+esc(a.level||'-')+'</td><td>'+esc(a.event||'-')+'</td><td>'+(a.issue?'#'+esc(String(a.issue)):'-')+'</td><td style="font-size:.8rem">'+esc(a.message||'-')+'</td></tr>';
 });}else{an.innerHTML='<tr><td colspan="5" class="empty">Keine Anomalien in den letzten 24h</td></tr>';}
}

async function loadLLM(){
 const d=await apiFetch('/api/v1/dashboard/llm').then(r=>r.json());
 const data=d.data||d;
 document.getElementById('l-calls').textContent=fmt(data.total_calls||0);
 document.getElementById('l-tokens').textContent=fmt(data.total_tokens||0);
 const cost=data.total_cost||0;
 document.getElementById('l-cost').textContent=typeof cost==='number'?cost.toFixed(4)+' EUR':String(cost);
 document.getElementById('l-provider').textContent=data.provider||'-';
 const activity=data.activity||{};
 const callText=c=>[c.task||'default',(c.provider||'?')+'/'+(c.model||'?')+(c.model_source==='request'?' (angefordert)':''),c.issue?'Issue #'+c.issue:'ohne Issue',c.correlation_id?'Run '+c.correlation_id:'ohne Run-Bindung','Start '+fmtTime(c.started_at)].join(' · ');
 const activeCalls=activity.calls||[];
 document.getElementById('l-current-calls').textContent=activity.status==='running'?activeCalls.map(callText).join(' | '):activity.status==='idle'?'idle — kein Call in dieser Runtime aktiv':'Nicht bekannt — keine aktuellen Runtime-Call-Facts';
 const lastCall=activity.last_call;
 document.getElementById('l-last-call').textContent=lastCall?callText(lastCall)+' · '+(lastCall.outcome||'unknown')+' · Ende '+fmtTime(lastCall.finished_at)+(lastCall.error_class?' · '+lastCall.error_class:''):'Noch kein Call in dieser Runtime beobachtet';
 renderModelCacheStatus(document.getElementById('l-model-cache'),data.model_cache||{});
 const trunc=document.getElementById('l-truncations');
 const truncs=data.truncations||[];
 if(truncs.length){
  const rows=truncs.slice(-5).reverse().map(t=>'<div><strong>'+(t.issue?'#'+esc(String(t.issue)):'ohne Issue')+'</strong> · '+esc(t.task||'default')+' · '+esc(t.provider||'-')+'/'+esc(t.model||'-')+' · '+esc(t.stop_reason||'length')+(t.content_max_tokens?' · Content-Limit '+fmt(t.content_max_tokens):'')+'</div>').join('');
  trunc.innerHTML='<div class="section" style="border-color:#ef4444"><h2 style="color:#ef4444">Ausgabe abgeschnitten</h2><p style="font-size:.8rem;margin-bottom:.4rem">Mindestens ein Provider beendete die Antwort am Tokenlimit. Teilantworten dürfen nicht als vollständiges Ergebnis behandelt werden.</p>'+rows+'</div>';
 }else{trunc.innerHTML='';}
 const kb=document.getElementById('l-keys');kb.innerHTML='';
 const keys=data.api_keys||[];
 if(keys.length){keys.forEach(k=>{
  const cls=k.status==='configured'?'ok':k.status==='missing'?'err':k.status==='url_only'?'warn':'';
  const ref=k.env_key?('$'+k.env_key):(k.url||'-');
  kb.innerHTML+='<tr><td>'+esc(k.provider||'-')+'</td><td>'+esc(k.model||'-')+'</td><td class="'+cls+'">'+esc(k.status||'-')+'</td><td style="font-size:.75rem">'+esc(ref)+'</td><td style="font-size:.75rem;color:#94a3b8">'+esc(k.note||'')+'</td></tr>';
 });}else{kb.innerHTML='<tr><td colspan="5" class="empty">Keine Provider-Konfig</td></tr>';}
 const sched=data.routing_schedule||{};
 const schedDiv=document.getElementById('l-schedule');
 if(sched.enabled){
  const activeCount=(sched.tasks||[]).filter(x=>x.active_now).length;
  schedDiv.textContent='Day/Night-Routing konfiguriert — '+(sched.tasks||[]).length+' Task-Zeitplan/-pläne · aktuell '+(activeCount?'Nacht-Route aktiv ('+activeCount+')':'Tag-Routen aktiv');
  schedDiv.style.color='#fbbf24';
 }else{schedDiv.textContent='Day/Night-Routing verfügbar, aber kein Task-Zeitplan konfiguriert';schedDiv.style.color='#64748b';}
 const rb=document.getElementById('l-routing');rb.innerHTML='';
 const routing=data.routing||[];
 if(Array.isArray(routing)&&routing.length){
  routing.forEach(r=>{
   const q=r.model_quality||{};const reason=q.reasoning||{};const suit=q.suitability||{};
   const guide=r.reasoning_guidance||{};const feedback=r.reasoning_feedback||{};
   let reasonText='kein Reasoning-Modell';
   if(guide.mode==='provider_default')reasonText='Provider-Default · 0 ist nicht „aus“';
   else if(guide.mode==='explicit_max_tokens')reasonText='explizit '+fmt(guide.reasoning_reserve||0)+' · Gesamt '+fmt(guide.effective_max_tokens||0);
   else if(guide.mode==='unsupported_provider')reasonText='Reserve wird nicht angewendet';
   else if(reason.is_reasoning)reasonText='Reasoning-Modell';
   const reasonWarn=guide.validation&&guide.validation!=='ok'&&guide.validation!=='not_applicable';
   const reasonDetail=[guide.semantics,guide.recommendation,feedback.note].filter(Boolean).join(' ');
   let quality='<span class="warn">keine Daten</span>';
   if(suit.available){const cls=suit.status==='suitable'?'ok':'warn';const label=suit.status==='overqualified'?'überqualifiziert':(suit.status==='below_threshold'?'unterqualifiziert':'geeignet');quality='<span class="'+cls+'">'+esc(label)+' · '+Number(suit.score).toFixed(1)+' '+esc(suit.index||'')+' / Schwelle '+Number(suit.threshold).toFixed(1)+'</span>';}
   rb.innerHTML+='<tr><td>'+esc(r.task||'-')+'</td><td>'+esc(r.provider||'-')+'</td><td>'+esc(r.model||'-')+'</td><td>'+(r.max_tokens!=null?fmt(r.max_tokens):'-')+'</td><td class="'+(reasonWarn?'warn':'')+'" title="'+esc(reasonDetail)+' · Erkennung: '+esc(reason.source||'unbekannt')+'">'+esc(reasonText)+'<br><span style="font-size:.68rem;color:#94a3b8">'+esc(guide.configuration_source||'')+(feedback.reasoning_samples?' · gemessen Ø '+esc(String(feedback.average_reasoning_tokens))+' / max '+esc(String(feedback.max_reasoning_tokens)):'')+'</span></td><td>'+quality+'</td><td>'+(r.temperature!=null?Number(r.temperature).toFixed(2):'-')+'</td><td>'+(r.timeout!=null?fmt(r.timeout):'-')+'</td></tr>';
  });
 }else{rb.innerHTML='<tr><td colspan="8" class="empty">Keine Routing-Daten</td></tr>';}
 const tb=document.getElementById('l-tasks');tb.innerHTML='';
 const tasks=data.by_task||[];
 if(Array.isArray(tasks)&&tasks.length){
  tasks.forEach(t=>{tb.innerHTML+='<tr><td>'+esc(t.task||t.name||'-')+'</td><td>'+fmt(t.calls||0)+'</td><td>'+fmt(t.tokens||0)+'</td><td>'+(t.cost!=null?Number(t.cost).toFixed(4):'-')+'</td></tr>';});
 }else if(typeof tasks==='object'&&!Array.isArray(tasks)){
  for(const[k,v]of Object.entries(tasks)){tb.innerHTML+='<tr><td>'+esc(k)+'</td><td>'+fmt(v.calls||0)+'</td><td>'+fmt(v.tokens||0)+'</td><td>'+(v.cost!=null?Number(v.cost).toFixed(4):'-')+'</td></tr>';}
 }
 if(!tb.innerHTML)tb.innerHTML='<tr><td colspan="4" class="empty">Keine LLM-Daten</td></tr>';
 const hb=document.getElementById('l-history');hb.innerHTML='';
 const hist=data.history||[];
 if(hist.length){hist.forEach(h=>{
  const guards=Array.isArray(h.guards)?h.guards:[];
  const tools=Array.isArray(h.tools_loaded)?h.tools_loaded:[];
  const ctx=Array.isArray(h.context_sections)?h.context_sections:[];
  const est=h.prompt_tokens_est;
  const parts=[];
  if(guards.length)parts.push('G:'+guards.length);
  if(tools.length)parts.push('T:'+tools.length);
  if(ctx.length)parts.push('C:'+ctx.length);
  if(est!=null)parts.push('~'+fmt(est)+'t');
  const tip='guards: '+(guards.join(', ')||'-')+'\\ntools_loaded: '+(tools.join(', ')||'-')+'\\ncontext_sections: '+(ctx.join(', ')||'-')+'\\nprompt_tokens_est: '+(est!=null?est:'-');
  const detailCell='<td title="'+esc(tip)+'" style="font-size:.75rem;color:#94a3b8;cursor:help">'+(parts.length?esc(parts.join(' '))+'</td>':'<span class="empty">-</span></td>');
  hb.innerHTML+='<tr><td>'+esc(fmtTime(h.timestamp||'-'))+'</td><td>'+esc(h.provider||'-')+'</td><td>'+esc(h.model||'-')+'</td><td>'+esc(h.task||'-')+'</td><td>'+(h.input_tokens!=null?fmt(h.input_tokens):'-')+'</td><td>'+(h.output_tokens!=null?fmt(h.output_tokens):'-')+'</td><td>'+(h.reasoning_tokens!=null?fmt(h.reasoning_tokens):'-')+'</td><td>'+(h.cached_tokens!=null?fmt(h.cached_tokens):'-')+'</td><td>'+(h.tokens!=null?fmt(h.tokens):'-')+'</td><td>'+(h.cost!=null?Number(h.cost).toFixed(4):'-')+'</td><td>'+(h.latency_ms!=null?fmt(h.latency_ms):'-')+'</td><td>'+(h.issue?'#'+esc(String(h.issue)):'-')+'</td>'+detailCell+'</tr>';
 });}else{hb.innerHTML='<tr><td colspan="13" class="empty">Keine LLM-Calls im Audit-Log</td></tr>';}
 const qb=document.getElementById('l-quality');qb.innerHTML='';
 const qual=data.quality||[];
 if(qual.length){qual.forEach(q=>{
  const sr=q.success_rate_pct;const cls=sr==null?'':sr>=80?'ok':sr>=50?'warn':'err';
  qb.innerHTML+='<tr><td>'+esc(q.provider||'-')+'</td><td>'+esc(q.model||'-')+'</td><td>'+esc(q.task||'-')+'</td><td style="font-size:.7rem">'+esc(qualitySeriesLabel(q))+'</td><td>'+fmt(q.calls||0)+'</td><td>'+fmt(q.unattributed_calls||0)+'</td><td>'+fmt(q.other_series_calls||0)+'</td><td>'+fmt(q.graded||0)+'</td><td>'+fmt(q.passed||0)+'</td><td>'+fmt(q.failed||0)+'</td><td class="'+cls+'">'+(sr!=null?sr+'%':'-')+'</td><td>'+(q.avg_score!=null?Number(q.avg_score).toFixed(2):'-')+'</td><td style="font-size:.75rem">'+esc(fmtTime(q.last_ts))+'</td></tr>';
 });}else{qb.innerHTML='<tr><td colspan="13" class="empty">Keine Quality-Korrelation moeglich</td></tr>';}
}

function renderModelCacheStatus(target,cache){
 if(!target)return;
 const labels={fresh:'aktuell',stale:'veraltet',upgrade_required:'altes Schema – Aktualisierung erforderlich',missing:'fehlt',unreadable:'nicht lesbar'};
 const status=cache.status||'missing';
 const cls=status==='fresh'?'ok':'warn';
 const fetched=cache.fetched_at?fmtTime(new Date(Number(cache.fetched_at)*1000).toISOString()):'nie';
 let benchmark=cache.benchmark_count==null?'Benchmarkstatus im alten Cache unbekannt':fmt(cache.benchmark_count)+' Modelle mit Benchmarkdaten';
 if(cache.benchmark_error)benchmark+=' · '+String(cache.benchmark_error);
 target.innerHTML='<h2>OpenRouter Modell- und Benchmarkdaten</h2><div class="'+cls+'"><strong>'+esc(labels[status]||status)+'</strong> · '+fmt(cache.count||0)+' Modelle · Stand '+esc(fetched)+' · Schema '+fmt(cache.schema_version||0)+'/'+fmt(cache.expected_schema_version||0)+'</div><div style="font-size:.75rem;color:#94a3b8;margin:.35rem 0">'+esc(benchmark)+'</div><button onclick="refreshOpenRouterCache()" style="background:#0ea5e9;color:#0f172a;border:none;padding:.4rem .8rem;border-radius:4px;cursor:pointer;font-weight:600">Modell- und Benchmarkdaten aktualisieren</button>';
}

async function refreshOpenRouterCache(){
 const target=document.getElementById('l-model-cache');
 if(target)target.innerHTML='<h2>OpenRouter Modell- und Benchmarkdaten</h2><div class="warn">Aktualisierung läuft …</div>';
 try{
  const r=await apiFetch('/api/v1/dashboard/llm/models/refresh',{method:'POST'});
  const j=await r.json();
  if(!r.ok||j.error)throw new Error(j.error||('HTTP '+r.status));
  const benchmarkText=j.benchmark_error?'Benchmarks nicht verfügbar: '+j.benchmark_error:fmt(j.benchmark_count||0)+' Modelle mit Benchmarks';
  showToast(fmt(j.count||0)+' Modelle aktualisiert; '+benchmarkText,j.benchmark_error?'warn':'ok');
  await loadLLM();
  return j;
 }catch(err){
  showToast('Modell-/Benchmarkdaten konnten nicht aktualisiert werden: '+String(err),'err');
  if(target)target.innerHTML='<h2>OpenRouter Modell- und Benchmarkdaten</h2><div class="err">Aktualisierung fehlgeschlagen: '+esc(String(err))+'</div><button onclick="refreshOpenRouterCache()">Erneut versuchen</button>';
  throw err;
 }
}

// #153: Quality-Tab — Heatmap Provider/Model x Task + Matrix + Param-Warnungen.
function qScoreColor(v){
 if(v==null)return '#1e293b';
 const pct=v*100;
 if(pct>=80)return '#065f46';
 if(pct>=60)return '#3f6212';
 if(pct>=40)return '#854d0e';
 if(pct>=20)return '#7c2d12';
 return '#7f1d1d';
}
function qualitySeriesLabel(q){
 return String(q.evidence_origin||'unbound_worktree')+' / '+String(q.scoring_policy_version||'legacy')+' / '+String(q.formula_version||'legacy');
}
async function loadQuality(){
 const d=await apiFetch('/api/v1/dashboard/quality').then(r=>r.json());
 const data=d.data||d;
 const wEl=document.getElementById('q-warnings');
 const warns=data.param_warnings||[];
 if(warns.length){
  let wh='<div class="section" style="border-left:3px solid #fbbf24"><h2 style="color:#fbbf24">Param-Size-Warnungen (min '+esc(String(data.min_params_b))+'B)</h2><ul style="margin:.3rem 0 0 1rem;font-size:.8rem">';
  warns.forEach(w=>{
   const why=w.reason==='unknown_size'?'Groesse unbekannt (nicht aus Modellname ableitbar)':('nur '+esc(String(w.params_b))+'B < '+esc(String(w.min_b))+'B');
   wh+='<li>'+esc(w.provider||'-')+'/'+esc(w.model||'-')+': '+why+'</li>';
  });
  wh+='</ul></div>';wEl.innerHTML=wh;
 }else{wEl.innerHTML='';}
 const series=data.selected_series||{};const attribution=data.attribution||{};
 const seriesEl=document.getElementById('q-series');
 seriesEl.innerHTML='<strong>Aktive Score-Serie:</strong> '+esc(qualitySeriesLabel(series))+' &middot; Serien-Calls '+fmt(attribution.series_calls||0)+' &middot; unattribuiert '+fmt(attribution.unattributed_calls||0)+' &middot; anderen Serien zugeordnet '+fmt(attribution.other_series_calls||0);
 const hm=data.heatmap||{tasks:[],rows:[]};
 const hEl=document.getElementById('q-heatmap');
 if((hm.rows||[]).length){
  let h='<table><thead><tr><th>Provider/Model</th>';
  (hm.tasks||[]).forEach(t=>{h+='<th>'+esc(t)+'</th>';});
  h+='</tr></thead><tbody>';
  hm.rows.forEach(r=>{
   h+='<tr><td>'+esc(r.provider||'-')+'/'+esc(r.model||'-')+'</td>';
   (r.cells||[]).forEach(c=>{
    const txt=c==null?'-':Math.round(c*100)+'%';
    h+='<td style="text-align:center;background:'+qScoreColor(c)+';color:#e2e8f0">'+txt+'</td>';
   });
   h+='</tr>';
  });
  h+='</tbody></table>';hEl.innerHTML=h;
 }else{hEl.innerHTML='<div class="empty">Noch keine Quality-Daten (LLM-Calls + Evals noetig)</div>';}
 const mb=document.getElementById('q-matrix');mb.innerHTML='';
 const rows=data.matrix||[];
 if(rows.length){rows.forEach(q=>{
  const sr=q.success_rate_pct;
  mb.innerHTML+='<tr><td>'+esc(q.provider||'-')+'</td><td>'+esc(q.model||'-')+'</td><td>'+esc(q.task||'-')+'</td><td style="font-size:.7rem">'+esc(qualitySeriesLabel(q))+'</td><td>'+(q.calls||0)+'</td><td>'+(q.unattributed_calls||0)+'</td><td>'+(q.other_series_calls||0)+'</td><td>'+(q.graded||0)+'</td><td>'+(q.passed||0)+'</td><td>'+(q.failed||0)+'</td><td>'+(sr!=null?sr+'%':'-')+'</td><td>'+(q.avg_score!=null?q.avg_score:'-')+'</td><td>'+(q.ewma_score!=null?q.ewma_score:'-')+'</td><td style="font-size:.7rem;color:#64748b">'+esc(fmtTime(q.last_ts))+'</td></tr>';
 });}else{mb.innerHTML='<tr><td colspan="14" class="empty">Keine Daten</td></tr>';}
}

// #230: SCM-Activity-Stream mit Bot/Human-Filter (client-seitig auf Cache).
let activityCache=[];
function renderActivity(){
 const f=(document.getElementById('act-filter')||{}).value||'all';
 const tb=document.getElementById('act-rows');if(!tb)return;
 const rows=activityCache.filter(r=>f==='all'||r.actor_type===f);
 if(!rows.length){tb.innerHTML='<tr><td colspan="7" class="empty">Keine SCM-Aktivitaet (Webhook konfiguriert?)</td></tr>';return;}
 let h='';
 rows.forEach(r=>{
  const tcls=r.actor_type==='bot'?'#60a5fa':'#fbbf24';
  const num=r.number?'#'+esc(String(r.number)):'-';
  const cell=r.url?'<a href="'+esc(r.url)+'" target="_blank" style="color:#93c5fd">'+num+'</a>':num;
  h+='<tr><td style="font-size:.75rem;color:#94a3b8">'+esc(fmtTime(r.ts))+'</td><td>'+esc(r.label||r.event||'-')+'</td><td>'+cell+'</td><td style="max-width:24rem;overflow:hidden;text-overflow:ellipsis">'+esc(r.title||'-')+'</td><td>'+esc(r.actor||'-')+'</td><td style="color:'+tcls+'">'+esc(r.actor_type||'-')+'</td><td style="font-size:.75rem;color:#64748b">'+esc(r.source||'-')+'</td></tr>';
 });
 tb.innerHTML=h;
}
async function loadActivity(){
 const d=await apiFetch('/api/v1/dashboard/activity').then(r=>r.json());
 const data=d.data||d;
 activityCache=data.activity||[];
 renderActivity();
}

async function loadWorkflow(){
 const d=await apiFetch('/api/v1/dashboard/workflow').then(r=>r.json());
 const data=d.data||d;
 const issues=data.issues||[];
 const recovered=data.recovered_count||0;
 const recBadge=document.getElementById('w-recovered');
 if(recBadge){recBadge.textContent=recovered>0?('Recovered: '+recovered):'';}
 const ib=document.getElementById('w-issues');ib.innerHTML='';
 if(issues.length){
  issues.forEach(i=>{const cls='badge badge-'+(i.status||'info');const num=i.number||0;
   const runs=i.runs_count!=null?fmt(i.runs_count):'-';
   const trend=i.trend||'';
   const trCol=trend==='recovered'?'#10b981':trend==='regressed'?'#ef4444':trend==='failed'?'#f59e0b':'#94a3b8';
   const trLabel=trend==='recovered'?'failed -> passed':trend==='regressed'?'passed -> failed':trend||'-';
   ib.innerHTML+='<tr data-issue="'+esc(String(num))+'" style="cursor:pointer"><td>#'+esc(String(num||'-'))+'</td><td><span class="'+cls+'">'+esc(i.status||'-')+'</span></td><td>'+esc(i.last_event||'-')+'</td><td>'+esc(fmtTime(i.timestamp||'-'))+'</td><td>'+runs+'</td><td style="color:'+trCol+'">'+esc(trLabel)+'</td></tr>';
  });
 }else{ib.innerHTML='<tr><td colspan="6" class="empty">Keine Issues</td></tr>';}
 const branches=data.branches||[];
 const bb=document.getElementById('w-branches');bb.innerHTML='';
 if(branches.length){
  branches.forEach(b=>{bb.innerHTML+='<tr><td>'+esc(b.name||'-')+'</td><td>'+(b.issue?'#'+esc(String(b.issue)):'-')+'</td><td>'+esc(b.status||'-')+'</td></tr>';});
 }else{bb.innerHTML='<tr><td colspan="3" class="empty">Keine Branches</td></tr>';}
}
document.getElementById('w-issues').addEventListener('click',e=>{
 const tr=e.target.closest('tr[data-issue]');if(!tr)return;
 const n=parseInt(tr.dataset.issue||'0',10);if(!n)return;
 loadWorkflowDetail(n);
});
document.getElementById('wd-close').addEventListener('click',()=>{
 document.getElementById('w-detail').style.display='none';
});
async function loadWorkflowDetail(n){
 const r=await apiFetch('/api/v1/dashboard/workflow/'+n);
 const panel=document.getElementById('w-detail');
 if(!r.ok){panel.style.display='block';document.getElementById('wd-num').textContent='#'+n;
  document.getElementById('wd-events').innerHTML='<tr><td colspan="7" class="empty">Keine Audit-Events fuer Issue #'+n+'</td></tr>';
  const trtb=document.getElementById('wd-test-runs');if(trtb){trtb.innerHTML='<tr><td colspan="6" class="empty">Keine Test-Runs</td></tr>';}
  const actb=document.getElementById('wd-acceptance-checks');if(actb){actb.innerHTML='<tr><td colspan="5" class="empty">Keine Acceptance Checks</td></tr>';}
  const grtb=document.getElementById('wd-gate-results');if(grtb){grtb.innerHTML='<tr><td colspan="5" class="empty">Keine Gate Results</td></tr>';}
  document.getElementById('wd-llm-detail').innerHTML='<tr><td colspan="10" class="empty">Keine LLM-Calls</td></tr>';
  const rb=document.getElementById('wd-runs');if(rb){rb.innerHTML='<tr><td colspan="7" class="empty">Keine Runs</td></tr>';}
  const rt=document.getElementById('wd-runs-trend');if(rt){rt.textContent='';}
  document.getElementById('wd-stages').innerHTML='';return;}
 const d=await r.json();
 panel.style.display='block';panel.scrollIntoView({behavior:'smooth',block:'nearest'});
 document.getElementById('wd-num').textContent='#'+(d.number||n);
 document.getElementById('wd-status').textContent=d.status||'-';
 document.getElementById('wd-branch').textContent=d.branch||'-';
 const sc=d.score||{};const sv=sc.value;const passed=sc.passed;
 const scoreStatus=sc.non_binding===true?' · NICHT BINDEND':(passed===true?' · LEGACY PASS':passed===false?' · LEGACY FAIL':'');
 document.getElementById('wd-score').textContent=(sv!=null?sv:'-')+(sc.baseline!=null?(' / '+sc.baseline):'')+scoreStatus;
 const llm=d.llm||{};
 document.getElementById('wd-llm-calls').textContent=fmt(llm.calls||0);
 document.getElementById('wd-llm-tokens').textContent=fmt(llm.tokens||0);
 document.getElementById('wd-llm-cost').textContent=(llm.cost!=null?Number(llm.cost).toFixed(4):'0.0000')+' EUR';
 const ldb=document.getElementById('wd-llm-detail');ldb.innerHTML='';
 const ldetail=Array.isArray(llm.calls_detail)?llm.calls_detail:[];
 if(ldetail.length){ldetail.slice().reverse().forEach(c=>{
  const guards=Array.isArray(c.guards)?c.guards.join(', '):'';
  const tools=Array.isArray(c.tools_loaded)?c.tools_loaded.join(', '):'';
  const ctx=Array.isArray(c.context_sections)?c.context_sections.join(', '):'';
  const est=c.prompt_tokens_est!=null?fmt(c.prompt_tokens_est):'-';
  const pm=esc(c.provider||'-')+(c.model?' / '+esc(c.model):'');
  ldb.innerHTML+='<tr><td style="font-size:.75rem">'+esc(fmtTime(c.timestamp||'-'))+'</td><td>'+esc(c.task||'-')+'</td><td style="font-size:.8rem">'+pm+'</td><td>'+fmt(c.tokens||0)+'</td><td>'+(c.cost!=null?Number(c.cost).toFixed(4):'-')+'</td><td>'+(c.latency_ms!=null?fmt(c.latency_ms)+'ms':'-')+'</td><td style="font-size:.75rem;color:#94a3b8">'+esc(guards||'-')+'</td><td style="font-size:.75rem;color:#94a3b8">'+esc(tools||'-')+'</td><td style="font-size:.75rem;color:#94a3b8">'+esc(ctx||'-')+'</td><td>'+est+'</td></tr>';
 });}else{ldb.innerHTML='<tr><td colspan="10" class="empty">Keine LLM-Calls</td></tr>';}
 const sb=document.getElementById('wd-stages');sb.innerHTML='';
 const stages=d.stages||{};
 ['plan','implement','llm','gates','quality','eval','healing','pr','review'].forEach(s=>{
  const st=stages[s]||{status:'pending',count:0,fail_count:0};
  const col=st.status==='done'?'#22c55e':st.status==='failed'?'#ef4444':st.status==='blocked'?'#b45309':'#475569';
  const file=st.file?' · '+esc(st.file):'';
  const reason=st.reason?'<div style="font-size:.7rem;margin-top:.2rem;max-width:28rem;white-space:normal">'+esc(st.event||'')+(st.event?': ':'')+esc(st.reason)+file+'</div>':'';
  sb.innerHTML+='<div style="background:'+col+';color:#fff;padding:.4rem .8rem;border-radius:4px;font-size:.8rem"><strong>'+esc(s)+': '+esc(st.status)+(st.count?' ('+st.count+(st.fail_count?'/'+st.fail_count+'!':'')+')':'')+'</strong>'+reason+'</div>';
 });
 const grb=document.getElementById('wd-gate-results');grb.innerHTML='';
 const gateResults=Array.isArray(d.gate_results)?d.gate_results:[];
 if(!gateResults.length){grb.innerHTML='<tr><td colspan="5" class="empty">Keine Gate Results</td></tr>';}
 else{gateResults.forEach(g=>{
  const state=g.status||'error';
  const labels={passed:'PASS',failed:'FAIL',error:'ERROR',missing_evidence:'MISSING EVIDENCE',not_applicable:'N/A',skipped_precondition:'SKIP',manual_pending:'MANUAL PENDING',not_evaluated:'NOT EVALUATED'};
  const cls=state==='passed'?'ok':state==='not_applicable'||state==='skipped_precondition'||state==='manual_pending'?'warn':'err';
  grb.innerHTML+='<tr><td>'+esc(g.gate||'-')+'</td><td>'+esc(g.authority||'-')+'</td><td>'+esc(g.phase||'-')+'</td><td><span class="'+cls+'">'+esc(labels[state]||state)+'</span></td><td>'+esc(g.reason||'-')+'</td></tr>';
 });}
 const tb=document.getElementById('wd-test-runs');tb.innerHTML='';
 const truns=Array.isArray(d.test_runs)?d.test_runs:[];
 if(!truns.length){tb.innerHTML='<tr><td colspan="6" class="empty">Keine Test-Runs</td></tr>';}
 else{truns.slice().reverse().forEach(t=>{
  const status=t.passed?'<span class="ok">PASS</span>':'<span class="err">FAIL</span>';
  const dur=t.duration_ms!=null?fmt(t.duration_ms)+'ms':'-';
  const exit=t.exit_code!=null?String(t.exit_code):'-';
  tb.innerHTML+='<tr><td>'+esc(fmtTime(t.timestamp||'-'))+'</td><td>'+esc(t.test_name||'-')+'</td><td>'+esc(t.runner||'-')+'</td><td>'+status+'</td><td>'+dur+'</td><td>'+esc(exit)+'</td></tr>';
 });}
 const acb=document.getElementById('wd-acceptance-checks');acb.innerHTML='';
 const checks=Array.isArray(d.acceptance_checks)?d.acceptance_checks:[];
 if(!checks.length){acb.innerHTML='<tr><td colspan="5" class="empty">Keine Acceptance Checks</td></tr>';}
 else{checks.slice().reverse().forEach(c=>{
  const state=c.status||'failed';
  const status=c.current===false?'<span style="color:#64748b">Historisch: '+esc(state)+'</span>':state==='passed'?'<span class="ok">PASS</span>':state==='manual_pending'?'<span class="warn">MANUAL PENDING</span>':'<span class="err">FAIL</span>';
  acb.innerHTML+='<tr><td>'+esc(fmtTime(c.timestamp||'-'))+'</td><td>'+esc(c.tag||'-')+'</td><td>'+esc(c.arg||'-')+'</td><td>'+status+'</td><td>'+esc(c.reason||'-')+'</td></tr>';
 });}
 const rb=document.getElementById('wd-runs');if(rb){rb.innerHTML='';
  const runs=Array.isArray(d.runs)?d.runs:[];
  if(!runs.length){rb.innerHTML='<tr><td colspan="7" class="empty">Keine Runs</td></tr>';}
  else{runs.forEach((rn,idx)=>{
   const score=rn.score!=null?Number(rn.score).toFixed(2):'-';
   let scoreCell=score;
   if(idx>0&&runs[idx-1].score!=null&&rn.score!=null){
    const delta=rn.score-runs[idx-1].score;
    const col=delta>0?'#10b981':delta<0?'#ef4444':'#94a3b8';
    const sign=delta>0?'+':'';
    scoreCell+=' <span style="font-size:.7rem;color:'+col+'">('+sign+delta.toFixed(2)+')</span>';
   }
   const stages=fmt(rn.stages_done||0)+(rn.stages_failed?'/'+rn.stages_failed+'!':'');
   const fs=rn.final_status||'-';
   const sCol=fs==='pr_created'?'#10b981':fs==='blocked'||fs==='aborted'||fs==='eval_failed'?'#ef4444':'#94a3b8';
   const pr=rn.pr_number?'#'+esc(String(rn.pr_number)):'-';
   rb.innerHTML+='<tr><td>'+(idx+1)+'</td><td style="font-size:.75rem">'+esc(fmtTime(rn.start_ts))+'</td><td style="font-size:.75rem">'+esc(fmtTime(rn.end_ts))+'</td><td>'+scoreCell+'</td><td>'+stages+'</td><td style="color:'+sCol+'">'+esc(fs)+'</td><td>'+pr+'</td></tr>';
  });}
 }
 const rt=document.getElementById('wd-runs-trend');
 if(rt){const tr=d.trend||'';
  if(tr==='recovered'){rt.textContent='(Trend: failed -> passed)';rt.style.color='#10b981';}
  else if(tr==='regressed'){rt.textContent='(Trend: passed -> failed)';rt.style.color='#ef4444';}
  else if(tr==='failed'){rt.textContent='(Trend: still failing)';rt.style.color='#f59e0b';}
  else if(tr==='passed'){rt.textContent='(Trend: passed)';rt.style.color='#10b981';}
  else{rt.textContent='';}
 }
 const eb=document.getElementById('wd-events');eb.innerHTML='';
 const evs=d.events||[];
 if(!evs.length){eb.innerHTML='<tr><td colspan="7" class="empty">Keine Events</td></tr>';return;}
 // #359: OWASP- + AI-Act-Zellen als click-expand markieren; jede Event-Zeile
 // bekommt eine zusaetzliche, initial versteckte Info-Zeile mit data-trail-info-for.
 // Tabelle hat 7 Spalten -> colspan="7" auf der Info-Zeile.
 const reversed=evs.slice().reverse();
 reversed.forEach((e,idx)=>{const lvl=(e.level||'').toLowerCase();
  const cls=lvl==='error'?'err':lvl==='warn'?'warn':'';
  const ow=e.owasp||'';
  const ai=e.ai_act||'';
  const owCell=ow?'<td class="trail-info-cell" data-trail-idx="'+idx+'" data-trail-kind="owasp" style="cursor:pointer;border-bottom:1px dotted #94a3b8" title="Klick fuer Erklaerung">'+esc(ow)+' &#9432;</td>':'<td>-</td>';
  const aiCell=ai?'<td class="trail-info-cell" data-trail-idx="'+idx+'" data-trail-kind="ai_act" style="cursor:pointer;border-bottom:1px dotted #94a3b8" title="Klick fuer Erklaerung">'+esc(ai)+' &#9432;</td>':'<td>-</td>';
  eb.innerHTML+='<tr><td>'+esc(fmtTime(e.timestamp||'-'))+'</td><td class="'+cls+'">'+esc(e.level||'-')+'</td><td>'+esc(e.category||'-')+'</td><td>'+esc(e.event||'-')+'</td><td>'+esc(e.message||'-')+'</td>'+owCell+aiCell+'</tr>'+
   '<tr class="trail-info-row" data-trail-info-for="'+idx+'" style="display:none"><td colspan="7" data-trail-info-content style="font-size:.75rem;background:#1e293b;padding:.5rem .75rem;color:#cbd5e1"></td></tr>';
 });
}

async function loadProblems(){
 const d=await apiFetch('/api/v1/dashboard/problems').then(r=>r.json());
 const data=d.data||d;
 allProblems=Array.isArray(data.problems)?data.problems:[];
 const counts=data.counts||{};
 document.getElementById('prob-count-error').textContent=fmt(counts.error||0);
 document.getElementById('prob-count-warn').textContent=fmt(counts.warn||0);
 document.getElementById('prob-count-historical').textContent=fmt(counts.historical||0);
 const cats=new Set();allProblems.forEach(p=>cats.add(p.category||'system'));
 const sel=document.getElementById('prob-cat');const cur=sel.value;
 sel.innerHTML='<option value="">Alle Kategorien</option>';
 [...cats].sort().forEach(c=>{sel.innerHTML+='<option value="'+esc(c)+'">'+esc(c)+'</option>';});
 sel.value=cur;
 filterProblems();
}
function filterProblems(){
 const level=document.getElementById('prob-level').value.toLowerCase();
 const category=document.getElementById('prob-cat').value.toLowerCase();
 const issue=document.getElementById('prob-issue').value.trim().replace(/^#/,'');
 const history=document.getElementById('prob-history').checked;
 const debug=document.getElementById('prob-debug').checked;
 document.querySelectorAll('.prob-debug-col').forEach(el=>{el.style.display=debug?'table-cell':'none';});
 const tb=document.getElementById('prob-body');tb.innerHTML='';
 let shown=0;
 const statusLabels={active:'aktiv',stale:'veraltet',resolved:'behoben',invalid_test_data:'ungültige alte Testdaten'};
 const typeLabels={scm_git:'Git/SCM',environment:'Umgebung',llm_provider:'LLM/Provider',configuration:'Konfiguration',security:'Sicherheit',workflow:'Workflow',product:'Samuel'};
 allProblems.forEach(p=>{
  if(level&&String(p.level||'').toLowerCase()!==level)return;
  if(category&&String(p.category||'').toLowerCase()!==category)return;
  const problemIssues=Array.isArray(p.issues)?p.issues.map(String):(p.issue?[String(p.issue)]:[]);
  if(issue&&!problemIssues.includes(issue))return;
  if(!history&&String(p.status||'active')!=='active')return;
  shown++;
  const lvl=String(p.level||'').toLowerCase();
  const cls=lvl==='error'?'err':'warn';
  const files=Array.isArray(p.files)&&p.files.length?p.files.join(', '):(p.file||'-');
  const debugText=[p.event,p.logger+(p.line?':'+p.line:''),p.exception,p.correlation_id].filter(Boolean).join(' · ');
  const steps=Array.isArray(p.next_steps)?p.next_steps.map(s=>'• '+s).join('\\n'):'-';
  const occurrences=Array.isArray(p.instances)?p.instances.slice(-20):[];
  const occurrenceDetails=occurrences.length?'<details><summary>Vorkommnisse (letzte '+esc(String(occurrences.length))+') · Korrelation belegt keine Kausalität</summary><ul>'+occurrences.map(i=>'<li>'+esc([fmtTime(i.timestamp),i.issue?'Issue #'+i.issue:'ohne Issue',i.correlation_id?'Korrelation '+i.correlation_id:'Korrelation unbekannt',i.line?'Zeile '+i.line:'',i.reason||'Diagnose unbekannt'].filter(Boolean).join(' · '))+'</li>').join('')+'</ul></details>':'';
  const summary='<strong>'+esc(p.title||p.reason||'-')+'</strong>'+(Number(p.count||1)>1?' <span class="badge">'+esc(String(p.count))+'×</span>':'')+'<br>Diagnose: '+esc(p.reason||'Nicht belegt')+(p.exception?' · Klasse: '+esc(p.exception):'')+'<br><span style="color:#94a3b8">Ursache: '+esc(p.cause||'-')+'<br>Auswirkung: '+esc(p.impact||'-')+'</span>'+occurrenceDetails;
  const issueText=problemIssues.length?problemIssues.map(i=>'#'+i).join(', '):'-';
  tb.innerHTML+='<tr><td style="font-size:.75rem">'+esc(fmtTime(p.last_seen||p.timestamp))+'</td><td>'+esc(statusLabels[p.status]||p.status||'aktiv')+'</td><td class="'+cls+'">'+esc(lvl||'-')+'</td><td>'+esc(typeLabels[p.problem_type]||p.problem_type||p.category||'-')+'</td><td>'+esc(issueText)+'</td><td>'+summary+'</td><td style="white-space:pre-line;font-size:.75rem">'+esc(steps)+'</td><td style="font-size:.75rem">'+esc(files)+'</td><td class="prob-debug-col" style="display:'+(debug?'table-cell':'none')+';font-size:.7rem;color:#94a3b8">'+esc(debugText||'-')+'</td></tr>';
 });
 if(!shown)tb.innerHTML='<tr><td colspan="9" class="empty">Keine passenden aktiven Probleme</td></tr>';
}
document.getElementById('prob-level').addEventListener('change',filterProblems);
document.getElementById('prob-cat').addEventListener('change',filterProblems);
document.getElementById('prob-issue').addEventListener('input',filterProblems);
document.getElementById('prob-history').addEventListener('change',filterProblems);
document.getElementById('prob-debug').addEventListener('change',filterProblems);

async function loadLogs(){
 const d=await apiFetch('/api/v1/dashboard/logs').then(r=>r.json());
 const data=d.data||d;
 allLogs=data.entries||[];
 if(!Array.isArray(allLogs))allLogs=[];
 const lc=data.level_counts||{};
 document.getElementById('log-count-error').textContent=fmt(lc.error||0);
 document.getElementById('log-count-warn').textContent=fmt(lc.warn||0);
 document.getElementById('log-count-info').textContent=fmt(lc.info||0);
 const cats=new Set();allLogs.forEach(l=>cats.add(l.category||'unknown'));
 const sel=document.getElementById('log-cat');const cur=sel.value;
 sel.innerHTML='<option value="">Alle Kategorien</option>';
 [...cats].sort().forEach(c=>{sel.innerHTML+='<option value="'+esc(c)+'">'+esc(c)+'</option>';});
 sel.value=cur;
 filterLogs();
}
function filterLogs(){
 const cat=document.getElementById('log-cat').value.toLowerCase();
 const lvl=document.getElementById('log-level').value.toLowerCase();
 const txt=document.getElementById('log-search').value.toLowerCase();
 const tb=document.getElementById('log-body');tb.innerHTML='';
 let shown=0;
 allLogs.forEach((l,idx)=>{
  if(cat&&(l.category||'').toLowerCase()!==cat)return;
  if(lvl&&(l.level||'').toLowerCase()!==lvl)return;
  const str=JSON.stringify(l).toLowerCase();
  if(txt&&!str.includes(txt))return;
  if(++shown>200)return;
  const lc=(l.level||'').toLowerCase();
  const cls=lc==='error'?'err':lc==='warn'||lc==='warning'?'warn':'';
  const meta=l.meta&&typeof l.meta==='object'?l.meta:{};
  const hasMeta=Object.keys(meta).length>0;
  const toggle=hasMeta?'<span class="log-toggle" style="cursor:pointer;color:#94a3b8;user-select:none">&#9654;</span>':'';
  const resolved=l.resolved_at?' <span style="background:#065f46;color:#d1fae5;padding:1px 6px;border-radius:3px;font-size:.7rem" title="Behoben am '+esc(fmtTime(l.resolved_at))+'">RESOLVED</span>':'';
  tb.innerHTML+='<tr class="log-row" data-meta-idx="'+idx+'"'+(hasMeta?' style="cursor:pointer"':'')+'>'+
   '<td>'+toggle+'</td>'+
   '<td>'+esc(fmtTime(l.timestamp||'-'))+'</td>'+
   '<td class="'+cls+'">'+esc(l.level||'-')+'</td>'+
   '<td>'+esc(l.category||'-')+'</td>'+
   '<td>'+esc(l.event||'-')+'</td>'+
   '<td>'+esc(l.message||'-')+resolved+'</td>'+
   '<td>'+(l.issue?'#'+esc(String(l.issue)):'-')+'</td></tr>'+
   '<tr class="log-meta-row" data-meta-for="'+idx+'" style="display:none"><td></td>'+
   '<td colspan="6" style="background:#0b1220;font-size:.75rem"><pre style="white-space:pre-wrap;margin:0;color:#cbd5e1">'+esc(JSON.stringify(meta,null,2))+'</pre></td></tr>';
 });
 if(!shown)tb.innerHTML='<tr><td colspan="7" class="empty">Keine Logs</td></tr>';
}
document.getElementById('log-cat').addEventListener('change',filterLogs);
document.getElementById('log-level').addEventListener('change',filterLogs);
document.getElementById('log-search').addEventListener('input',filterLogs);
document.getElementById('log-body').addEventListener('click',e=>{
 const row=e.target.closest('tr.log-row');if(!row)return;
 const idx=row.dataset.metaIdx;if(idx==null)return;
 const meta=document.querySelector('tr.log-meta-row[data-meta-for="'+idx+'"]');
 if(!meta)return;
 const open=meta.style.display!=='none';
 meta.style.display=open?'none':'table-row';
 const tog=row.querySelector('.log-toggle');if(tog)tog.innerHTML=open?'&#9654;':'&#9660;';
});

// #359: Click-Expand fuer OWASP/AI-Act-Codes im Audit-Trail (Workflow-Detail).
// Lazy-laedt die Compliance-Legende beim ersten Klick und togglet die info-row.
document.getElementById('wd-events').addEventListener('click',async e=>{
 const cell=e.target.closest('.trail-info-cell');if(!cell)return;
 const idx=cell.dataset.trailIdx;if(idx==null)return;
 const row=document.querySelector('.trail-info-row[data-trail-info-for="'+idx+'"]');
 if(!row)return;
 const open=row.style.display!=='none';
 if(open){row.style.display='none';return;}
 // Beide Beschreibungen auf einmal zeigen — egal welche Zelle in der Zeile geklickt wurde
 await ensureLegend();
 const evRow=cell.closest('tr');
 const cells=evRow.querySelectorAll('.trail-info-cell');
 let html='';
 cells.forEach(c=>{
  const kind=c.dataset.trailKind;
  // Zellen-Text ist "<code> ⓘ" — nur den Code wollen wir.
  const raw=(c.textContent||'').trim();
  const txt=raw.endsWith('ⓘ')?raw.slice(0,-1).trim():raw;
  if(kind==='owasp'){const desc=owaspDesc(txt);if(desc)html+='<div style="color:#fbbf24"><strong>OWASP '+esc(txt)+':</strong> '+esc(desc)+'</div>';}
  if(kind==='ai_act'){const desc=aiActDesc(txt);const ob=obligationBadge(aiActObligation(txt));if(desc)html+='<div style="color:#60a5fa;margin-top:.2rem"><strong>'+esc(txt)+':</strong> '+(ob?ob+' ':'')+esc(desc)+'</div>';}
 });
 if(!html)html='<span style="color:#94a3b8;font-style:italic">Keine Beschreibung in Compliance-Legende.</span>';
 const target=row.querySelector('[data-trail-info-content]');
 if(target)target.innerHTML=html;
 row.style.display='table-row';
});

let secOwasp=[];
async function loadSecurity(){
 const d=await apiFetch('/api/v1/dashboard/security').then(r=>r.json());
 const data=d.data||d;
 document.getElementById('sec-total').textContent=fmt(data.total_events||0);
 const pct=data.classified_pct!=null?data.classified_pct+'%':'-';
 document.getElementById('sec-classified').textContent=pct;
 document.getElementById('sec-risks').textContent=fmt(data.active_risks||0);
 const tamper=data.tamper_events||[];
 const banner=document.getElementById('sec-tamper-banner');
 if(tamper.length){
  const external=tamper.filter(t=>t.classification==='external_signature').length;
  const internal=tamper.filter(t=>t.classification==='internal_integrity').length;
  const other=tamper.length-external-internal;
  const parts=[];
  if(external)parts.push(external+' externe Signatur-/Webhook-Prüfung(en)');
  if(internal)parts.push(internal+' interne Integritätsverletzung(en)');
  if(other)parts.push(other+' sonstige Sicherheitsereignis(se)');
  banner.style.display='block';
  banner.innerHTML='<strong>SECURITY ALERT &mdash; '+esc(parts.join('; '))+'</strong>';
 }else{banner.style.display='none';banner.innerHTML='';}
 const bp=data.branch_protection||{};
 const bpDiv=document.getElementById('sec-branch-protection');
 const bpBranch=esc(bp.branch||'main');
 if(!bp.available){
  bpDiv.innerHTML='<div class="empty">SCM unterstuetzt Branch-Protection nicht oder ist nicht verbunden ('+bpBranch+')</div>';
 }else if(bp.error==='permission_denied'){
  bpDiv.innerHTML='<div style="color:#f59e0b"><strong>EINGESCHRAENKT</strong> &mdash; '+bpBranch+' (Branchschutz-Read abgewiesen; Operator prueft Endpoint und Credential gezielt. Mindestrecht unbekannt; das restliche Dashboard bleibt verfuegbar)</div>';
 }else if(bp.error){
  bpDiv.innerHTML='<div style="color:#f87171"><strong>FEHLER</strong> &mdash; '+bpBranch+' (SCM-Request fehlgeschlagen, siehe Logs)</div>';
 }else if(bp.protected){
  let html='<div style="color:#10b981"><strong>AKTIV</strong> &mdash; '+bpBranch+'</div>';
  const rules=bp.rules||{};
  const flags=[];
  if(rules.required_approvals!=null)flags.push('approvals: '+esc(String(rules.required_approvals)));
  if(rules.enable_status_check)flags.push('status-checks');
  if(rules.dismiss_stale_approvals)flags.push('dismiss-stale');
  if(rules.require_signed_commits)flags.push('signed-commits');
  if(flags.length)html+='<div style="font-size:.75rem;color:#94a3b8;margin-top:.25rem">'+esc(flags.join(' | '))+'</div>';
  bpDiv.innerHTML=html;
 }else{
  bpDiv.innerHTML='<div style="color:#f59e0b"><strong>FEHLT</strong> &mdash; '+bpBranch+' ist ungeschuetzt. Operator: Branch-Protection auf SCM einrichten.</div>';
 }
 secOwasp=data.owasp||[];
 const ob=document.getElementById('sec-owasp');ob.innerHTML='';
 if(secOwasp.length){secOwasp.forEach((o,i)=>{const has=(o.recent||[]).length>0;
  ob.innerHTML+='<tr data-owasp-idx="'+i+'" style="cursor:'+(has?'pointer':'default')+'"><td>'+esc(o.id||'-')+'</td><td>'+esc(o.category||o.name||'-')+'</td><td>'+fmt(o.count||0)+'</td><td style="font-size:.75rem;color:#94a3b8">'+esc(o.last||'-')+'</td></tr>';
 });}
 else{ob.innerHTML='<tr><td colspan="4" class="empty">Keine OWASP-Daten</td></tr>';}
 document.getElementById('sec-owasp-recent').innerHTML='';
 const barrier=data.barriers||[];
 const bb=document.getElementById('sec-barrier');bb.innerHTML='';
 if(barrier.length){
  // #359: OWASP-Spalte als click-expand markieren analog zum Audit-Trail.
  // Tabelle hat 7 Spalten -> colspan="7" auf der Info-Zeile.
  const reversed=barrier.slice().reverse();
  reversed.forEach((b,idx)=>{
   const a=(b.action||'').toLowerCase();
   const bg=a==='blocked'?'background:rgba(239,68,68,.15)':a==='warn'?'background:rgba(251,191,36,.12)':'';
   const ow=b.owasp||'';
   const owCell=ow?'<td class="barrier-info-cell" data-barrier-idx="'+idx+'" style="cursor:pointer;border-bottom:1px dotted #94a3b8" title="Klick fuer Erklaerung">'+esc(ow)+' &#9432;</td>':'<td>-</td>';
   bb.innerHTML+='<tr style="'+bg+'"><td>'+esc(fmtTime(b.timestamp||'-'))+'</td><td>'+(b.issue?'#'+esc(String(b.issue)):'-')+'</td><td>'+esc(b.step||'-')+'</td><td>'+esc(b.event||'-')+'</td><td>'+esc(b.action||'-')+'</td>'+owCell+'<td>'+esc(b.detail||'-')+'</td></tr>'+
    '<tr class="barrier-info-row" data-barrier-info-for="'+idx+'" style="display:none"><td colspan="7" data-barrier-info-content style="font-size:.75rem;background:#1e293b;padding:.5rem .75rem;color:#cbd5e1"></td></tr>';
  });
 }
 else{bb.innerHTML='<tr><td colspan="7" class="empty">Keine Schranken-Events</td></tr>';}
 const otel=data.otel_calls||[];
 const ot=document.getElementById('sec-otel');ot.innerHTML='';
 if(otel.length){otel.forEach(o=>{
  ot.innerHTML+='<tr><td>'+esc(fmtTime(o.timestamp||'-'))+'</td><td>'+esc(o['gen_ai.system']||'-')+'</td><td>'+esc(o['gen_ai.request.model']||'-')+'</td><td>'+(o['gen_ai.usage.input_tokens']!=null?fmt(o['gen_ai.usage.input_tokens']):'-')+'</td><td>'+(o['gen_ai.usage.output_tokens']!=null?fmt(o['gen_ai.usage.output_tokens']):'-')+'</td><td>'+(o['gen_ai.usage.total_tokens']!=null?fmt(o['gen_ai.usage.total_tokens']):'-')+'</td><td>'+(o['gen_ai.client.operation.duration']!=null?Number(o['gen_ai.client.operation.duration']).toFixed(0):'-')+'</td><td>'+esc(o['gen_ai.response.finish_reasons']||'-')+'</td><td>'+esc(o.task||'-')+'</td></tr>';
 });}
 else{ot.innerHTML='<tr><td colspan="9" class="empty">Keine OTel-Calls</td></tr>';}
 const tb2=document.getElementById('sec-tamper');tb2.innerHTML='';
 if(tamper.length){tamper.forEach(t=>{const remediation=Array.isArray(t.remediation)?t.remediation.join(' · '):(t.remediation||'-');const subject=[t.run?'Run '+t.run:'',t.issue?'#'+t.issue:''].filter(Boolean).join(' / ')||'-';tb2.innerHTML+='<tr><td>'+esc(fmtTime(t.ts||'-'))+'</td><td><strong>'+esc(t.summary||t.event||'-')+'</strong><br><span style="font-size:.7rem;color:#94a3b8">'+esc(t.event||'-')+' · '+esc(t.level||'-')+' · '+esc(t.owasp||'-')+'</span></td><td>'+esc(t.source||'-')+'<br><span style="font-size:.7rem;color:#94a3b8">'+esc(t.component||'-')+'</span></td><td>'+esc(t.detail||'-')+'<br><span style="font-size:.7rem;color:#94a3b8">Auswirkung: '+esc(t.impact||'-')+'<br>Maßnahme: '+esc(remediation)+'</span></td><td>'+esc(subject)+'</td></tr>';});}
 else{tb2.innerHTML='<tr><td colspan="5" class="empty">Keine Tamper-Events</td></tr>';}
}
document.getElementById('sec-owasp').addEventListener('click',e=>{
 const tr=e.target.closest('tr[data-owasp-idx]');if(!tr)return;
 const idx=parseInt(tr.dataset.owaspIdx,10);const o=secOwasp[idx];
 if(!o||!(o.recent||[]).length)return;
 const box=document.getElementById('sec-owasp-recent');
 let html='<div class="section" style="margin-top:.5rem"><h3 style="font-size:.85rem;color:#94a3b8;text-transform:uppercase;margin-bottom:.5rem">'+esc(o.id)+' &mdash; '+esc(o.category)+' (Recent '+o.recent.length+')</h3><table><thead><tr><th>Zeit</th><th>Event</th><th>Message</th><th>Issue</th></tr></thead><tbody>';
 o.recent.forEach(r=>{html+='<tr><td>'+esc(fmtTime(r.timestamp||'-'))+'</td><td>'+esc(r.event||'-')+'</td><td>'+esc(r.message||'-')+'</td><td>'+(r.issue?'#'+esc(String(r.issue)):'-')+'</td></tr>';});
 html+='</tbody></table></div>';
 box.innerHTML=html;box.scrollIntoView({behavior:'smooth',block:'nearest'});
});

// #359: Click-Expand fuer OWASP-Code im Schranken-Protokoll. Pattern analog
// zum Audit-Trail-Handler weiter oben — eine Helper-freie Inline-Variante.
document.getElementById('sec-barrier').addEventListener('click',async e=>{
 const cell=e.target.closest('.barrier-info-cell');if(!cell)return;
 const idx=cell.dataset.barrierIdx;if(idx==null)return;
 const row=document.querySelector('.barrier-info-row[data-barrier-info-for="'+idx+'"]');
 if(!row)return;
 const open=row.style.display!=='none';
 if(open){row.style.display='none';return;}
 await ensureLegend();
 const raw=(cell.textContent||'').trim();
 const txt=raw.endsWith('ⓘ')?raw.slice(0,-1).trim():raw;
 const desc=owaspDesc(txt);
 const target=row.querySelector('[data-barrier-info-content]');
 if(target){
  target.innerHTML=desc
   ?'<div style="color:#fbbf24"><strong>OWASP '+esc(txt)+':</strong> '+esc(desc)+'</div>'
   :'<span style="color:#94a3b8;font-style:italic">Keine Beschreibung in Compliance-Legende.</span>';
 }
 row.style.display='table-row';
});

async function loadCompliance(){
 // #252: OWASP Top-10 + EU AI Act Artikel-Erklärungen
 const d=await apiFetch('/api/v1/dashboard/compliance/legend').then(r=>r.json());
 const ot=document.getElementById('comp-owasp');ot.innerHTML='';
 (d.owasp||[]).forEach(r=>{
  ot.innerHTML+='<tr><td><strong>'+esc(r.id||'-')+'</strong></td><td>'+esc(r.name||'-')+'</td><td style="font-family:monospace;font-size:.75rem;color:#94a3b8">'+esc(r.key||'-')+'</td><td>'+esc(r.description||'-')+'</td></tr>';
 });
 // #373/#374: aktive Deployment-Risikoklasse sichtbar + editierbar machen —
 // sonst wirkt ein "freiwillig" an einem Hochrisiko-Deployment irrefuehrend.
 const rcDiv=document.getElementById('aiact-riskclass');
 if(rcDiv){
  const rc=d.ai_act_risk_class||'';
  const src=d.ai_act_risk_class_source||'';
  const high=rc==='high_risk';
  const locked=src==='env';
  const opts=['minimal_risk','limited_risk','high_risk'].map(k=>'<option value="'+k+'"'+(k===rc?' selected':'')+'>'+esc(riskClassLabel(k))+'</option>').join('');
  let html='Deployment-Risikoklasse: <select id="rc-select" onchange="saveRiskClass(this.value)"'+(locked?' disabled':'')+' style="background:#020617;color:#e2e8f0;border:1px solid #334155;border-radius:3px;padding:.15rem .3rem;font-size:.8rem">'+opts+'</select>';
  if(locked)html+=' <span style="color:#94a3b8">per <code>SAMUEL_RISK_CLASS</code> env fixiert</span>';
  html+='<div style="margin-top:.3rem;color:#94a3b8">'
   +(high
     ?'Die High-Risk-Artikel (12-15) sind hier <strong>Pflicht</strong> — SAMUEL liefert die Compliance-Instrumente des ueberwachten Systems.'
     :'Pflicht ist nur Art. 50 (gilt fuer alle Systeme); Art. 12-15 adressieren Hochrisiko-Systeme und sind hier freiwillig uebererfuellt.')
   +'</div>';
  rcDiv.innerHTML=html;
 }
 // #270: LLM-Code-Kennzeichnung (externe Sichtbarkeit) — Toggle + Verbosity.
 const atDiv=document.getElementById('aiact-attribution');
 if(atDiv){
  const a=d.attribution||{};
  const on=!!a.enabled;const locked=!!a.locked;const vb=a.verbosity||'minimal';
  const vopts=['minimal','full'].map(k=>'<option value="'+k+'"'+(k===vb?' selected':'')+'>'+k+'</option>').join('');
  let h='<label class="toggle" style="vertical-align:middle"><input type="checkbox" id="attr-toggle" '+(on?'checked':'')+(locked?' disabled':'')+' onchange="saveAttribution()"><span class="slider"></span></label>';
  h+=' <span style="vertical-align:middle">Externe Kennzeichnung '+(on?'<strong style="color:#10b981">an</strong>':'<strong style="color:#fbbf24">aus</strong>')+'</span>';
  h+=' &nbsp; Ausfuehrlichkeit: <select id="attr-verbosity" onchange="saveAttribution()"'+(locked?' disabled':'')+' style="background:#020617;color:#e2e8f0;border:1px solid #334155;border-radius:3px;padding:.15rem .3rem;font-size:.8rem">'+vopts+'</select>';
  if(locked)h+='<div style="margin-top:.3rem;color:#fbbf24">Bei Risikoklasse <code>high_risk</code> ist die Kennzeichnung Pflicht (Art. 50) und nicht abschaltbar.</div>';
  else if(!on)h+='<div style="margin-top:.3rem;color:#fbbf24">Hinweis: KI-generierter Code wird extern nicht als solcher gekennzeichnet. Die Audit-Spur bleibt erhalten.</div>';
  atDiv.innerHTML=h;
 }
 const at=document.getElementById('comp-aiact');at.innerHTML='';
 (d.ai_act||[]).forEach(r=>{
  at.innerHTML+='<tr><td><strong>'+esc(r.article||'-')+'</strong></td><td>'+(obligationBadge(r.obligation)||'-')+'</td><td>'+esc(r.description||'-')+'</td></tr>';
 });
}

// #374: Deployment-Risikoklasse persistieren (config/compliance.json). Bei
// Erfolg Cache invalidieren und Tab neu laden, damit Badges + Tooltip-Cache
// die abgeleiteten Obligationen neu rechnen.
async function saveRiskClass(v){
 try{
  const r=await apiFetch('/api/v1/settings/risk-class',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({risk_class:v})});
  const j=await r.json();
  if(r.ok){showToast('Risikoklasse = '+riskClassLabel(v),'ok');complianceCache=null;await loadCompliance();}
  else{showToast('Fehler: '+(j.error||JSON.stringify(j)),'err');}
 }catch(err){showToast('Netzwerk-Fehler: '+err,'err');}
}

// #270: LLM-Code-Kennzeichnung persistieren (features.json + privacy.json).
// Backend sperrt bei high_risk (Art. 50). Warnung beim Deaktivieren als Toast.
async function saveAttribution(){
 const t=document.getElementById('attr-toggle');const vs=document.getElementById('attr-verbosity');
 if(!t)return;const enabled=t.checked;
 try{
  const body={enabled:enabled};if(vs)body.verbosity=vs.value;
  const r=await apiFetch('/api/v1/settings/attribution',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const j=await r.json();
  if(r.ok){if(j.warning){showToast(j.warning,'err');}else{showToast('Kennzeichnung gespeichert','ok');}complianceCache=null;await loadCompliance();}
  else{showToast('Fehler: '+(j.error||JSON.stringify(j)),'err');t.checked=!enabled;}
 }catch(err){showToast('Netzwerk-Fehler: '+err,'err');}
}

// #334: Dead-Letter-Queue read-only anzeigen.
async function loadDlq(){
 const el=document.getElementById('set-dlq');if(!el)return;
 try{
  const d=await apiFetch('/api/v1/dashboard/dlq').then(r=>r.json());
  const rows=d.entries||[];
  if(!rows.length){el.innerHTML='<div class="empty">DLQ leer</div>';return;}
  let h='<table><thead><tr><th>Zeit</th><th>Event</th><th>Handler</th><th>Fehler</th><th>ID</th></tr></thead><tbody>';
  rows.forEach(r=>{
   h+='<tr><td style="font-size:.75rem;color:#94a3b8">'+esc(fmtTime(r.ts))+'</td><td>'+esc(r.event_name||'-')+'</td><td style="font-size:.75rem;color:#94a3b8">'+esc(r.handler||'-')+'</td><td style="color:#fca5a5">'+esc(r.error||'-')+'</td><td style="font-family:monospace;font-size:.7rem;color:#64748b">'+esc((r.id||'').slice(0,8))+'</td></tr>';
  });
  h+='</tbody></table>';
  el.innerHTML=h;
 }catch(e){el.innerHTML='<div class="empty">Fehler beim Laden</div>';}
}

const identityRoles=['viewer','auditor','operator','administrator'];
function identityRoleInputs(prefix,selected){
 const active=new Set(selected||[]);
 return identityRoles.map(role=>'<label style="margin-right:.7rem"><input type="checkbox" data-identity-role="'+esc(prefix)+'" value="'+role+'" '+(active.has(role)?'checked':'')+'> '+role+'</label>').join('');
}
function selectedIdentityRoles(prefix){
 return Array.from(document.querySelectorAll('input[data-identity-role="'+prefix+'"]:checked')).map(item=>item.value);
}
async function identityMutation(url,method,body){
 const response=await apiFetch(url,{method:method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
 const data=await response.json();
 if(!response.ok){showToast('Identity: '+(data.code||data.error||'Fehler'),'err');return null;}
 return data;
}
async function reauthenticateIdentity(){
 const input=document.getElementById('identity-current-password');
 const password=input?input.value:'';
 if(!password){showToast('Aktuelles Passwort erforderlich','warn');return;}
 const data=await identityMutation('/api/v1/auth/reauth','POST',{password:password});
 if(input)input.value='';
 if(data){updateActor(data.actor);showToast('Sitzung frisch authentisiert','ok');await loadIdentityPanel();}
}
async function createIdentityUser(){
 const username=document.getElementById('identity-new-username').value.trim();
 const password=document.getElementById('identity-new-password').value;
 const roles=selectedIdentityRoles('new');
 const data=await identityMutation('/api/v1/admin/users','POST',{username:username,password:password,roles:roles});
 document.getElementById('identity-new-password').value='';
 if(data){showToast('Benutzer angelegt','ok');await loadIdentityPanel();}
}
async function saveIdentityUser(principalId){
 const disabled=document.getElementById('identity-disabled-'+principalId).checked;
 const roles=selectedIdentityRoles(principalId);
 const data=await identityMutation('/api/v1/admin/users/'+principalId,'POST',{roles:roles,disabled:disabled});
 if(data){showToast('Benutzer aktualisiert; bestehende Sitzungen widerrufen','ok');await loadIdentityPanel();}
}
async function revokeIdentitySession(sessionId){
 const data=await identityMutation('/api/v1/admin/sessions/'+sessionId,'DELETE',{});
 if(data){showToast(data.revoked?'Sitzung widerrufen':'Sitzung war bereits widerrufen','ok');await loadIdentityPanel();}
}
async function revokeAllIdentitySessions(){
 const confirmation=document.getElementById('identity-revoke-confirmation').value;
 const data=await identityMutation('/api/v1/admin/sessions/revoke-all','POST',{confirmation:confirmation});
 if(data){updateActor(null);showToast(data.revoked+' Sitzungen widerrufen','ok');await requestApiKey();}
}
async function createIdentityToken(){
 const name=document.getElementById('identity-token-name').value.trim();
 const permissions=document.getElementById('identity-token-permissions').value.split(',').map(value=>value.trim()).filter(Boolean);
 const lifetime=Number(document.getElementById('identity-token-lifetime').value||0);
 const data=await identityMutation('/api/v1/admin/tokens','POST',{name:name,permissions:permissions,lifetime_seconds:lifetime});
 const output=document.getElementById('identity-token-output');
 if(data&&output){output.textContent='Token nur jetzt kopieren: '+data.token;output.style.display='block';}
}
async function revokeIdentityToken(tokenId){
 const data=await identityMutation('/api/v1/admin/tokens/'+tokenId,'DELETE',{});
 if(data){showToast(data.revoked?'Automation-Token widerrufen':'Token war bereits widerrufen','ok');await loadIdentityPanel();}
}
async function loadIdentityPanel(){
 const root=document.getElementById('set-identity');if(!root)return;
 try{
  await ensureAuthMode();
  if(authMode!=='local_identity'){
   root.innerHTML='<p class="setup-note">Legacy-API-Key-Modus. Lokale Identitäten zuerst per CLI bootstrappen und nach vollständiger Client-Inventur explizit umstellen.</p>';
   return;
  }
  const sessionResponse=await apiFetch('/api/v1/auth/session');
  if(!sessionResponse.ok){root.innerHTML='<div class="empty">Nicht angemeldet</div>';return;}
  const sessionData=await sessionResponse.json();updateActor(sessionData.actor);
  const permissions=new Set((currentActor||{}).permissions||[]);
  let html='<p class="setup-note">Angemeldet als <strong>'+esc(currentActor.username||'-')+'</strong> · Rollen: '+esc((currentActor.roles||[]).join(', ')||'keine')+'</p>';
  html+='<div style="display:flex;gap:.4rem;flex-wrap:wrap;margin-bottom:.8rem"><input id="identity-current-password" type="password" autocomplete="current-password" placeholder="Aktuelles Passwort"><button onclick="reauthenticateIdentity()">Frisch authentisieren</button></div>';
  if(!permissions.has('identity:manage')){root.innerHTML=html+'<div class="empty">Keine Identitätsverwaltungs-Permission</div>';return;}
  const[usersResponse,sessionsResponse,tokensResponse]=await Promise.all([apiFetch('/api/v1/admin/users'),apiFetch('/api/v1/admin/sessions'),apiFetch('/api/v1/admin/tokens')]);
  const users=usersResponse.ok?(await usersResponse.json()).users||[]:[];
  const sessions=sessionsResponse.ok?(await sessionsResponse.json()).sessions||[]:[];
  const tokens=tokensResponse.ok?(await tokensResponse.json()).tokens||[]:[];
  html+='<h3 style="margin:.7rem 0">Benutzer und Rollen</h3>';
  users.filter(user=>user.kind==='user').forEach(user=>{
   html+='<div class="flag-row" style="display:block"><strong>'+esc(user.username)+'</strong> <span class="badge '+(user.disabled?'badge-err':'badge-ok')+'">'+(user.disabled?'deaktiviert':'aktiv')+'</span><div style="margin:.4rem 0">'+identityRoleInputs(user.principal_id,user.roles)+'</div><label><input id="identity-disabled-'+user.principal_id+'" type="checkbox" '+(user.disabled?'checked':'')+'> deaktiviert</label> <button data-identity-save="'+user.principal_id+'">Speichern</button></div>';
  });
  html+='<div class="section" style="margin-top:.7rem"><h3>Benutzer anlegen</h3><input id="identity-new-username" autocomplete="off" placeholder="Benutzername"> <input id="identity-new-password" type="password" autocomplete="new-password" placeholder="Initialpasswort"><div style="margin:.5rem 0">'+identityRoleInputs('new',[])+'</div><button onclick="createIdentityUser()">Anlegen</button></div>';
  html+='<h3 style="margin:.7rem 0">Sitzungen</h3><table><thead><tr><th>Principal</th><th>Zuletzt</th><th>Ablauf</th><th>Status</th><th></th></tr></thead><tbody>';
  sessions.forEach(row=>{html+='<tr><td>'+esc(row.principal_id)+'</td><td>'+esc(fmtTime(row.last_seen_at))+'</td><td>'+esc(fmtTime(row.expires_at))+'</td><td>'+(row.revoked_at?'widerrufen':'aktiv')+'</td><td>'+(row.revoked_at?'':'<button data-session-revoke="'+row.session_id+'">Widerrufen</button>')+'</td></tr>';});
  html+='</tbody></table><div style="margin-top:.6rem"><input id="identity-revoke-confirmation" placeholder="REVOKE ALL SESSIONS"> <button onclick="revokeAllIdentitySessions()">Alle Sitzungen widerrufen</button></div>';
  html+='<div class="section" style="margin-top:.8rem"><h3>Automation-Token einmalig erzeugen</h3><input id="identity-token-name" placeholder="Clientname"> <input id="identity-token-permissions" placeholder="diagnostics:read, audit:read" style="min-width:260px"> <input id="identity-token-lifetime" type="number" min="1" max="31536000" value="3600"><button onclick="createIdentityToken()">Erzeugen</button><div id="identity-token-output" class="warn-item" style="display:none;margin-top:.5rem;overflow-wrap:anywhere"></div></div>';
  html+='<table><thead><tr><th>Automation</th><th>Permissions</th><th>Ablauf</th><th>Status</th><th></th></tr></thead><tbody>';
  tokens.forEach(row=>{html+='<tr><td>'+esc(row.username)+'</td><td>'+esc((row.permissions||[]).join(', '))+'</td><td>'+esc(fmtTime(row.expires_at))+'</td><td>'+(row.revoked_at?'widerrufen':'aktiv')+'</td><td>'+(row.revoked_at?'':'<button data-token-revoke="'+row.token_id+'">Widerrufen</button>')+'</td></tr>';});
  html+='</tbody></table>';
  root.innerHTML=html;
  root.querySelectorAll('button[data-identity-save]').forEach(button=>button.addEventListener('click',()=>saveIdentityUser(button.dataset.identitySave)));
  root.querySelectorAll('button[data-session-revoke]').forEach(button=>button.addEventListener('click',()=>revokeIdentitySession(button.dataset.sessionRevoke)));
  root.querySelectorAll('button[data-token-revoke]').forEach(button=>button.addEventListener('click',()=>revokeIdentityToken(button.dataset.tokenRevoke)));
 }catch(error){root.innerHTML='<div class="empty">Identity-Status konnte nicht geladen werden.</div>';}
}

async function loadSettings(){
 loadDlq();
 loadIdentityPanel();
 const[sd,st]=await Promise.all([
  apiFetch('/api/v1/dashboard/settings').then(r=>r.json()),
  apiFetch('/api/v1/dashboard/status').then(r=>r.json())
 ]);
 const sdata=sd.data||sd;
 const configuration=sdata.configuration||{};
 const configMode=document.getElementById('set-config-mode');
 if(configMode){
  const writable=configuration.writable===true;
  const restart=configuration.restart_required===true;
  configMode.innerHTML='<span class="badge '+(writable?'warn':'ok')+'">'+esc(configuration.mode||'production')+'</span> '
   +(writable?'Schreibmodus ausdrücklich aktiv. Änderungen werden erst nach Neustart des Produktionsdienstes wirksam.':'Konfiguration eingefroren: Produktionsdienst stoppen; mit derselben Konfiguration das lokale Dashboard ausdrücklich mit --configuration-mode setup starten; prüfen und speichern; Setup beenden; Produktionsruntime neu erzeugen; gespeicherte/wirksame Werte und Produktions-Freeze prüfen. Details: Installationsanleitung Abschnitt 4.3.')
   +(restart?' <span class="badge warn">Neustart erforderlich</span>':'')
   +'<div style="font-size:.72rem;color:#64748b;margin-top:.4rem">Quelle: '+esc(configuration.source||'-')+' · gespeichert: '+esc(configuration.stored_config_digest||'-')+' · wirksam: '+esc(configuration.effective_config_digest||'-')+'</div>';
 }
 const syncLabelsButton=document.getElementById('btn-sync-labels');
 if(syncLabelsButton)syncLabelsButton.disabled=configuration.writable!==true;
 const extension=sdata.extensions||{};
 const extensionDiv=document.getElementById('set-documentation-extension');
 if(extensionDiv){
  const disabled=configuration.writable!==true?' disabled':'';
  const manifest=extension.manifest_path||'';
  extensionDiv.innerHTML='<div style="display:grid;grid-template-columns:auto minmax(220px,1fr);gap:.55rem;align-items:center;max-width:760px">'
   +'<label>Aktiviert</label><input id="extension-enabled" type="checkbox" '+(extension.enabled?'checked':'')+disabled+'>'
   +'<label>Erforderlich</label><input id="extension-required" type="checkbox" '+(extension.required?'checked':'')+disabled+'>'
   +'<label>Manifestpfad</label><input id="extension-manifest-path" value="'+esc(manifest)+'" placeholder="/srv/samuel/extensions/documentation/capability.json"'+disabled+'>'
   +'<label>Gespeichert</label><div><span class="badge '+(extension.blocked?'badge-err':(extension.available?'badge-ok':'warn'))+'">'+esc(extension.status||'unknown')+'</span> '+esc(extension.reason||'')+'</div>'
   +'<label>Wirksam</label><div><span class="badge '+(extension.effective_blocked?'badge-err':(extension.effective_available?'badge-ok':'warn'))+'">'+esc(extension.effective_status||'unknown')+'</span> '+esc(extension.effective_reason||'')+'</div>'
   +'<label></label><button onclick="saveDocumentationExtension()"'+disabled+'>Speichern</button></div>'
   +'<p style="font-size:.72rem;color:#64748b;margin-top:.5rem">Contract '+esc(extension.contract_version||'1.0')+' · advisory · Änderung wird erst nach Neustart wirksam.</p>';
 }
 window.__modelCache=sdata.model_cache||{};
 const flagsRaw=sdata.flags||sdata.feature_flags||[];
 const fDiv=document.getElementById('set-flags');fDiv.innerHTML='';
 let flagItems=[];
 if(Array.isArray(flagsRaw)){flagItems=flagsRaw.map(f=>({key:f.key,enabled:!!f.enabled,description:f.description||''}));}
 else if(typeof flagsRaw==='object'){flagItems=Object.keys(flagsRaw).map(k=>({key:k,enabled:!!flagsRaw[k],description:''}));}
 if(flagItems.length){flagItems.forEach(f=>{
  const desc=f.description?' <span style="color:#64748b;font-size:.75rem">'+esc(f.description)+'</span>':'';
  const row=document.createElement('div');row.className='flag-row';
  row.innerHTML='<span>'+esc(f.key)+desc+'</span><label class="toggle"><input type="checkbox" data-flag="'+esc(f.key)+'" '+(f.enabled?'checked':'')+'><span class="slider"></span></label>';
  fDiv.appendChild(row);
 });
 fDiv.querySelectorAll('input[data-flag]').forEach(inp=>{inp.addEventListener('change',async e=>{
  const name=e.target.getAttribute('data-flag');const enabled=e.target.checked;
  try{
   const r=await apiFetch('/api/v1/settings/flag',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,enabled:enabled})});
   const j=await r.json();
   if(r.ok){showToast('Flag '+name+' = '+enabled,'ok');}
   else{showToast('Fehler: '+(j.error||JSON.stringify(j)),'err');e.target.checked=!enabled;}
  }catch(err){showToast('Netzwerk-Fehler: '+err,'err');e.target.checked=!enabled;}
 });});
 if(configuration.writable!==true){fDiv.querySelectorAll('input[data-flag]').forEach(inp=>{inp.disabled=true;});}
 }else{fDiv.innerHTML='<div class="empty">Keine Feature Flags</div>';}
 const globalCfg=sdata.llm_global_config||{};
 const globalDiv=document.getElementById('set-llm-global');
 const globalProviders=globalCfg.providers||[];
 const selectedFallbacks=globalCfg.fallbacks||[];
 const providerOptions=globalProviders.map(p=>'<option value="'+esc(p)+'"'+(p===globalCfg.provider?' selected':'')+'>'+esc(p)+'</option>').join('');
 globalDiv.innerHTML='<div style="display:grid;grid-template-columns:auto minmax(180px,1fr);gap:.5rem;align-items:start;max-width:620px">'+
  '<label>Aktiv</label><div><strong>'+esc(globalCfg.effective_provider||globalCfg.provider||'-')+'</strong> <span style="font-size:.7rem;color:#64748b">('+esc(globalCfg.provider_source||'config')+')</span></div>'+
  '<label>Default-Provider</label><select id="set-llm-default">'+providerOptions+'</select>'+
  '<label>Fallback-Kette</label><div><input id="set-llm-fallbacks" value="'+esc(selectedFallbacks.join(', '))+'" placeholder="openrouter, ollama" style="width:100%"><div style="font-size:.7rem;color:#64748b;margin-top:.25rem">Kommagetrennt in Ausführungsreihenfolge; Änderungen greifen nach Neustart des Agenten.</div></div>'+
  '<label></label><button onclick="saveLLMGlobalConfig()" style="background:#10b981;color:#0f172a;border:none;padding:.4rem .8rem;border-radius:4px;cursor:pointer;font-weight:600;width:max-content">Save default/fallback</button></div>';
 if(configuration.writable!==true){globalDiv.querySelectorAll('input,select,button').forEach(el=>{el.disabled=true;});}
 const llmCfg=sdata.llm_config||[];
 const cDiv=document.getElementById('set-llm-config');cDiv.innerHTML='';
 if(Array.isArray(llmCfg)&&llmCfg.length){llmCfg.forEach(row=>{
  const task=row.task||'?';
  const prov=row.provider||'-';
  const model=row.model||'-';
  // #312: Edit-Icon mit Spacing + Bleistift-Symbol statt "edit" — Layout-Fix.
  const editIcon=configuration.writable===true?' <button onclick="openLLMTaskEditor(\\''+esc(task)+'\\')" title="Konfiguration bearbeiten" style="background:transparent;border:1px solid #334155;cursor:pointer;color:#0ea5e9;font-size:.8rem;margin-left:.75rem;padding:.15rem .5rem;border-radius:3px">&#9998; edit</button>':'';
  // #348: zeige system_prompt + Source-Badge (welche Cascade-Stufe greift)
  const sp=row.system_prompt||'';
  const promptCol=sp?(' &middot; <span style="color:#cbd5e1">'+esc(sp)+'</span>'+_promptSourceBadge(row.system_prompt_source||{})):'';
  cDiv.innerHTML+='<div class="flag-row" id="llm-row-'+esc(task)+'" style="align-items:center"><span style="font-weight:600">'+esc(task)+editIcon+'</span><span style="color:#94a3b8" id="llm-display-'+esc(task)+'">'+esc(prov)+' / '+esc(model)+promptCol+'</span></div><div id="llm-edit-'+esc(task)+'" style="display:none;padding:.5rem 0 .75rem 1rem;font-size:.8rem"></div>';
 });}else{cDiv.innerHTML='<div class="empty">Keine LLM-Config</div>';}
 // Save current rows for editor
 window.__llmCfg=llmCfg;
 const apiKeys=sdata.api_keys||[];
 const kDiv=document.getElementById('set-api-keys');kDiv.innerHTML='';
 if(Array.isArray(apiKeys)&&apiKeys.length){apiKeys.forEach(k=>{
  const provider=k.provider||'?';
  const status=k.status||'unknown';
  const color=status==='configured'?'#10b981':(status==='missing'?'#ef4444':'#f59e0b');
  // #311-followup: Balance-Anzeige (live bei DeepSeek/OpenRouter, "not provided by API" bei anderen)
  let balanceHtml='';
  if(k.balance!==undefined&&k.balance!==null){
   balanceHtml=' <span style="color:#10b981;font-weight:600">Balance: $'+Number(k.balance).toFixed(4)+'</span>';
   if(k.balance_note==='live')balanceHtml+=' <span style="color:#64748b;font-size:.7rem">(live)</span>';
  }else if(k.balance_note){
   balanceHtml=' <span style="color:#64748b;font-size:.75rem">'+esc(k.balance_note)+'</span>';
  }
  kDiv.innerHTML+='<div class="flag-row"><span>'+esc(provider)+'</span><span style="color:'+color+'">'+esc(status)+balanceHtml+'</span></div>';
 });}else{kDiv.innerHTML='<div class="empty">Keine API-Keys konfiguriert</div>';}
 const ws=st.transfer_warnings||[];
 const wDiv=document.getElementById('set-warnings');
 const wSec=document.getElementById('set-warnings-section');
 if(ws.length){wSec.style.display='';wDiv.innerHTML='';
  ws.forEach(w=>{wDiv.innerHTML+='<div class="warn-item">'+esc(w.provider||'?')+': '+esc(w.warning||w.message||JSON.stringify(w))+'</div>';});
 }else{wSec.style.display='none';}
}

async function saveDocumentationExtension(){
 const enabled=document.getElementById('extension-enabled');
 const required=document.getElementById('extension-required');
 const manifest=document.getElementById('extension-manifest-path');
 if(!enabled||!required||!manifest)return;
 const manifestPath=manifest.value.trim();
 try{
  const response=await apiFetch('/api/v1/settings/extensions/documentation',{
   method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({enabled:enabled.checked,required:required.checked,manifest_path:manifestPath||null})
  });
  const body=await response.json();const data=body.data||body;
  if(response.ok&&data.updated){
   showToast('Documentation Extension gespeichert — Neustart erforderlich','warn');
   await loadSettings();
  }else{showToast('Fehler: '+(data.error||JSON.stringify(data)),'err');}
 }catch(err){showToast('Netzwerk-Fehler: '+err,'err');}
}

// #309/#312: Per-task LLM configuration editor.
const LLM_PROVIDERS=['claude','deepseek','gemini','openai','openrouter','ollama','lmstudio','manual'];
const LLM_PROMPTS=['','senior_python.md','planner.md','docs_writer.md','healer.md','log_analyst.md','reviewer.md','analyst.md'];

// #348: Source-Badge fuer den system_prompt — zeigt auf einen Blick welche
// Cascade-Stufe greift (package, operator-generic, operator-provider:X,
// operator-model:Y) damit der Operator weiss ob sein per-Provider-Override
// gewinnt oder unbeachtet bleibt.
function _promptSourceBadge(src){
 const s=(src&&src.source)||'none';
 let color='#64748b',label=s;
 if(s==='package'){color='#64748b';}
 else if(s==='operator-generic'){color='#0ea5e9';}
 else if(s.indexOf('operator-provider:')===0){color='#3b82f6';}
 else if(s.indexOf('operator-model:')===0){color='#10b981';}
 else if(s==='none'){color='#ef4444';label='not found';}
 const path=(src&&src.path)||'';
 const title=path?('Active source: '+s+(path?' ('+path+')':'')):'No prompt source resolved';
 return ' <span title="'+esc(title)+'" style="color:'+color+';font-size:.7rem;border:1px solid '+color+';padding:.05rem .35rem;border-radius:3px;margin-left:.4rem">'+esc(label)+'</span>';
}

// #312: Provider-spezifische Default-URLs. Lokale Provider brauchen URL,
// API-Provider haben fixe Endpoints (Override nur fuer Sonderfaelle).
const LLM_PROVIDER_DEFAULTS={
 claude:    {url:'',                              urlRequired:false, urlNote:'fix: api.anthropic.com'},
 openai:    {url:'',                              urlRequired:false, urlNote:'fix: api.openai.com'},
 deepseek:  {url:'',                              urlRequired:false, urlNote:'fix: api.deepseek.com'},
 gemini:    {url:'',                              urlRequired:false, urlNote:'fix: generativelanguage.googleapis.com'},
 openrouter:{url:'',                              urlRequired:false, urlNote:'fix: openrouter.ai/api/v1 (Gateway, vendor/model-IDs)'},
 ollama:    {url:'http://localhost:11434',        urlRequired:true,  urlNote:'lokaler Ollama-Endpoint'},
 lmstudio:  {url:'http://localhost:1234/v1',      urlRequired:true,  urlNote:'lokaler LM-Studio-Endpoint'},
 manual:    {url:'',                              urlRequired:false, urlNote:'Filesystem-only'}
};

async function openLLMTaskEditor(task){
 // #351-fix: Library-Liste BEVOR der HTML gerendert wird, damit
 // _buildPromptByProviderSection -> _promptByProviderRow die Selects
 // sofort mit allen Library-Prompts fuellen kann (vorher: Race -> leer).
 await _ensurePromptListLoaded(/*force=*/false);
 const cfg=(window.__llmCfg||[]).find(r=>r.task===task)||{};
 const editDiv=document.getElementById('llm-edit-'+task);
 if(!editDiv)return;
 const opts=p=>LLM_PROVIDERS.map(x=>'<option value="'+x+'"'+(x===p?' selected':'')+'>'+x+'</option>').join('');
 const propts=p=>LLM_PROMPTS.map(x=>'<option value="'+x+'"'+(x===(p||'')?' selected':'')+'>'+(x||'(none)')+'</option>').join('');
 // #313: Model wird Dropdown statt Input — Liste kommt von /api/v1/dashboard/llm/models
 editDiv.innerHTML='<div style="display:grid;grid-template-columns:auto 1fr;gap:.4rem;max-width:560px">'+
  '<label>Provider</label><select id="ed-prov-'+task+'" onchange="onLLMProviderChange(\\''+task+'\\')">'+opts(cfg.provider||'')+'</select>'+
  '<label>Model</label><div style="display:flex;gap:.3rem"><select id="ed-model-'+task+'" onchange="updateModelAssessment(\\''+task+'\\')" style="flex:1"><option value="'+esc(cfg.model||'')+'">'+esc(cfg.model||'(loading...)')+'</option></select>'+
  '<button onclick="refreshModelsForProvider(\\''+task+'\\')" title="OpenRouter-Modell-, Reasoning- und Benchmarkdaten aktualisieren" style="background:#1e293b;border:1px solid #334155;color:#e2e8f0;cursor:pointer;padding:.15rem .5rem;border-radius:3px;font-size:.75rem">&#x21bb;</button></div>'+
  '<label></label><span id="ed-modelnote-'+task+'" style="color:#64748b;font-size:.7rem"></span>'+
  '<label>base_url</label><input id="ed-baseurl-'+task+'" value="'+esc(cfg.base_url||'')+'" placeholder="auto-fill je Provider">'+
  '<label></label><span id="ed-urlnote-'+task+'" style="color:#64748b;font-size:.7rem"></span>'+
  '<label>timeout (s)</label><input id="ed-timeout-'+task+'" value="'+esc(cfg.timeout||'')+'" type="number">'+
  // #315: system_prompt-Dropdown dynamisch + View/Edit-Buttons.
  // #348: Source-Badge zeigt welche Cascade-Stufe greift (package/operator-...).
  '<label>system_prompt</label><div style="display:flex;gap:.3rem;align-items:center;flex-wrap:wrap"><select id="ed-sp-'+task+'" style="flex:1">'+propts(cfg.system_prompt)+'</select>'+
  '<button onclick="viewSystemPrompt(\\''+task+'\\')" title="Prompt-Inhalt anzeigen" style="background:#1e293b;border:1px solid #334155;color:#e2e8f0;cursor:pointer;padding:.15rem .5rem;border-radius:3px;font-size:.75rem">View</button>'+
  '<button onclick="editSystemPrompt(\\''+task+'\\')" title="Prompt-Inhalt editieren" style="background:#1e293b;border:1px solid #0ea5e9;color:#0ea5e9;cursor:pointer;padding:.15rem .5rem;border-radius:3px;font-size:.75rem">Edit</button>'+
  '<span id="ed-sp-src-'+task+'">'+_promptSourceBadge(cfg.system_prompt_source||{})+'</span>'+
  '</div>'+
  // #351 L3: faltbare Per-Provider-Override-Section
  '<label></label>'+_buildPromptByProviderSection(task,cfg.system_prompt_by_provider||{})+
  '<label>max_tokens</label><input id="ed-maxt-'+task+'" value="'+esc(cfg.max_tokens||'')+'" type="number">'+
  '<label>reasoning_reserve</label><input id="ed-reason-'+task+'" value="'+esc(cfg.reasoning_reserve||0)+'" type="number" min="0">'+
  '<label></label><span style="color:#64748b;font-size:.7rem">0 = keine explizite Steuerung, nicht „Reasoning aus“. Eine Zahl reserviert nur bei OpenRouter zusätzliche Output-Tokens; Content max bleibt separat.</span>'+
  '<label>Reasoning-Hinweis</label><div style="font-size:.72rem;color:#94a3b8">'+esc((cfg.reasoning_guidance||{}).semantics||'Keine Metadaten')+'<br><span class="warn">'+esc((cfg.reasoning_guidance||{}).recommendation||'')+'</span></div>'+
  '<label>Kostenhinweis</label><input id="ed-cost-advisory-'+task+'" type="checkbox"'+(cfg.cost_advisory_enabled!==false?' checked':'')+'>'+
  '<label>Überqualifiziert-Marge</label><input id="ed-overqual-margin-'+task+'" value="'+esc(cfg.overqualification_margin_ratio==null?0.2:cfg.overqualification_margin_ratio)+'" type="number" min="0" max="1" step="0.01">'+
  '<label></label><span style="color:#64748b;font-size:.7rem">Relative Marge auf die Task-Schwelle; 0,20 bedeutet bei Schwelle 50: überqualifiziert ab 60. Der Hinweis ändert das gewählte Modell nicht.</span>'+
  '<label>temperature</label><input id="ed-temp-'+task+'" value="'+esc(cfg.temperature||'')+'" type="number" step="0.1">'+
  '</div>'+
  '<div id="ed-urlerr-'+task+'" style="color:#ef4444;font-size:.75rem;margin-top:.25rem;display:none">URL erforderlich fuer diesen Provider</div>'+
  // #316: Schedule (day/night switch).
  buildScheduleSection(task,cfg.schedule||{})+
  '<div id="ed-testresult-'+task+'" style="margin-top:.5rem;display:none;font-size:.8rem"></div>'+
  '<div style="margin-top:.5rem"><button onclick="saveLLMTaskConfig(\\''+task+'\\')" style="background:#10b981;color:#0f172a;border:none;padding:.4rem .8rem;border-radius:4px;cursor:pointer;font-weight:600">Save</button> '+
  '<button onclick="testLLMConnection(\\''+task+'\\')" id="ed-testbtn-'+task+'" style="background:#0ea5e9;color:#0f172a;border:none;padding:.4rem .8rem;border-radius:4px;cursor:pointer;margin-left:.5rem;font-weight:600">Test</button> '+
  '<button onclick="closeLLMTaskEditor(\\''+task+'\\')" style="background:#475569;color:#fff;border:none;padding:.4rem .8rem;border-radius:4px;cursor:pointer;margin-left:.5rem">Cancel</button></div>';
 editDiv.style.display='block';
 onLLMProviderChange(task,/*initial=*/true);
 loadModelsForProvider(task,/*currentModel=*/cfg.model||'');
 // #315: Prompts-Liste dynamisch laden (Package + Operator-Override)
 loadPromptsForTask(task,cfg.system_prompt||'');
 // #316: Schedule-Models laden falls schedule.provider gesetzt ist
 if(cfg.schedule&&cfg.schedule.provider){
  loadScheduleModels(task);
 }
}

// #315: Dynamisch befuellen — zeigt Package- und Operator-Prompts mit Source-Hint.
// #351: speichert die Liste zusaetzlich in window.__llmPromptList damit die
// Per-Provider-Override-Selects (_promptByProviderRow) sie wiederverwenden.
async function loadPromptsForTask(task,currentPrompt){
 await _ensurePromptListLoaded(/*force=*/true);
 const sel=document.getElementById('ed-sp-'+task);
 if(!sel)return;
 const list=window.__llmPromptList||[];
 if(!list.length)return;  // Fallback: behalte statische Liste
 const opts=['<option value=""'+(currentPrompt?'':' selected')+'>(none)</option>'];
 list.forEach(p=>{
  const tag=p.source==='operator'?' [override]':'';
  const sel2=p.name===currentPrompt?' selected':'';
  opts.push('<option value="'+esc(p.name)+'"'+sel2+'>'+esc(p.name)+esc(tag)+'</option>');
 });
 sel.innerHTML=opts.join('');
 // Per-Provider-Selects neu rendern damit neue Library-Files auftauchen.
 _refreshPromptByProviderSelects();
}

// #351-fix: zentrale Library-Liste laden + cachen. Race-Condition zwischen
// editor-render und loadPromptsForTask hat dazu gefuehrt, dass die
// Per-Provider-Selects beim ersten Editor-Open leer waren.
async function _ensurePromptListLoaded(force){
 if(!force && Array.isArray(window.__llmPromptList) && window.__llmPromptList.length) return;
 try{
  const r=await apiFetch('/api/v1/dashboard/llm/prompts');
  const j=await r.json();const d=j.data||j;
  window.__llmPromptList=(d&&d.prompts)||[];
 }catch(e){window.__llmPromptList=window.__llmPromptList||[];}
}

// #351 L3: Per-Provider-Override-Section — Map { provider: filename } im Editor.
// Render initial vorhandene Eintraege als Liste; "+" fuegt eine neue Zeile;
// Remove entfernt eine Zeile. saveLLMTaskConfig sammelt alle Zeilen ein.
function _buildPromptByProviderSection(task,byProvider){
 const entries=byProvider&&typeof byProvider==='object'?Object.entries(byProvider):[];
 const rows=entries.map((kv,i)=>_promptByProviderRow(task,i,kv[0],kv[1])).join('');
 return '<div id="ed-spbp-wrap-'+task+'" style="grid-column:1/3;border-top:1px dashed #334155;padding-top:.4rem;margin-top:.2rem">'+
  '<div style="display:flex;align-items:center;gap:.4rem;margin-bottom:.3rem">'+
   '<span style="font-weight:600;color:#e2e8f0;font-size:.8rem">Per-Provider Overrides</span>'+
   '<span style="color:#64748b;font-size:.7rem">verschiedene Prompts pro Provider zuweisen (z.B. lokale 7B-Modelle bekommen ausfuehrlichere Prompts)</span>'+
  '</div>'+
  '<div id="ed-spbp-rows-'+task+'">'+rows+'</div>'+
  '<button onclick="addPromptByProviderRow(\\''+task+'\\')" type="button" style="background:#1e293b;border:1px solid #334155;color:#e2e8f0;cursor:pointer;padding:.15rem .5rem;border-radius:3px;font-size:.75rem;margin-top:.3rem">+ Provider-Override</button>'+
 '</div>';
}

function _promptByProviderRow(task,idx,provider,filename){
 const provs=LLM_PROVIDERS.map(p=>'<option value="'+p+'"'+(p===provider?' selected':'')+'>'+p+'</option>').join('');
 // Filename-Liste kommt aus window.__llmPromptList (durch loadPromptsForTask
 // gefuellt). Wenn noch nicht geladen, nur den aktuell gespeicherten Wert
 // anbieten — wird beim naechsten Editor-Open dann komplett.
 const list=Array.isArray(window.__llmPromptList)?window.__llmPromptList:[];
 const allNames=new Set(list.map(p=>p.name));
 if(filename)allNames.add(filename);
 const fileOpts='<option value="">(prompt waehlen...)</option>'+
  Array.from(allNames).sort().map(n=>'<option value="'+esc(n)+'"'+(n===filename?' selected':'')+'>'+esc(n)+'</option>').join('');
 return '<div class="spbp-row" data-task="'+esc(task)+'" data-idx="'+idx+'" style="display:flex;gap:.3rem;align-items:center;margin-bottom:.2rem">'+
  '<select class="spbp-prov" style="background:#020617;color:#e2e8f0;border:1px solid #334155;border-radius:3px;padding:.15rem .3rem;font-size:.75rem"><option value="">(provider...)</option>'+provs+'</select>'+
  '<span style="color:#64748b">&rarr;</span>'+
  '<select class="spbp-name" style="flex:1;background:#020617;color:#e2e8f0;border:1px solid #334155;border-radius:3px;padding:.15rem .3rem;font-size:.75rem">'+fileOpts+'</select>'+
  '<button onclick="this.parentElement.remove()" type="button" title="Eintrag entfernen" style="background:#7f1d1d;color:#fff;border:none;cursor:pointer;padding:.15rem .4rem;border-radius:3px;font-size:.75rem">&times;</button>'+
 '</div>';
}

async function addPromptByProviderRow(task){
 const wrap=document.getElementById('ed-spbp-rows-'+task);
 if(!wrap)return;
 // Library-Liste sicherstellen damit der filename-select nicht leer rendert.
 await _ensurePromptListLoaded(/*force=*/false);
 const idx=wrap.querySelectorAll('.spbp-row').length;
 wrap.insertAdjacentHTML('beforeend',_promptByProviderRow(task,idx,'',''));
}

// Sammelt alle Per-Provider-Eintraege im Editor zu einem dict { provider: filename }.
// Leere Provider-Werte oder Filenames werden uebersprungen (UX: User kann Zeile
// hinzufuegen, vor dem Save aber nicht ausfuellen — die wird stillschweigend ignoriert).
function _collectPromptByProvider(task){
 const wrap=document.getElementById('ed-spbp-rows-'+task);
 if(!wrap)return {};
 const out={};
 wrap.querySelectorAll('.spbp-row').forEach(row=>{
  const prov=row.querySelector('.spbp-prov');
  const fname=row.querySelector('.spbp-name');
  const p=prov?prov.value.trim():'';
  const f=fname?fname.value.trim():'';
  if(!p||!f)return;
  // Filename kommt jetzt aus dem Library-Select; .md-Endung ist
  // bei Library-Eintraegen garantiert, fuer den Edge-Case aber sicher.
  out[p]=f.endsWith('.md')?f:(f+'.md');
 });
 return out;
}

// Refreshe alle bekannten Per-Provider-Selects (z.B. nach einem Library-
// Save im Modal): rendere die existing Map neu, damit die neuen Library-
// Eintraege im Dropdown auftauchen.
function _refreshPromptByProviderSelects(){
 ['planning','implementation','review','healing','evaluation','default'].forEach(task=>{
  const wrap=document.getElementById('ed-spbp-rows-'+task);
  if(!wrap)return;
  // Aktuellen Stand einsammeln
  const map=_collectPromptByProvider(task);
  // Rows neu rendern (mit aktualisierter window.__llmPromptList)
  const rows=Object.entries(map).map((kv,i)=>_promptByProviderRow(task,i,kv[0],kv[1])).join('');
  wrap.innerHTML=rows;
 });
}

// #316: Schedule section (day/night switch).
function buildScheduleSection(task,schedule){
 const active=!!(schedule&&schedule.active);
 const fromV=(schedule&&schedule.from)||'22:00';
 const toV  =(schedule&&schedule.to)  ||'06:00';
 const provV=(schedule&&schedule.provider)||'';
 const modelV=(schedule&&schedule.model)||'';
 const provOpts=LLM_PROVIDERS.map(x=>'<option value="'+x+'"'+(x===provV?' selected':'')+'>'+x+'</option>').join('');
 const noteHtml='<span style="color:#64748b;font-size:.7rem">Mitternacht-Uebergang (z.B. 22:00 - 06:00) wird automatisch behandelt.</span>';
 return '<div style="margin-top:.6rem;border-top:1px dashed #334155;padding-top:.5rem">'+
  '<div style="font-weight:600;color:#e2e8f0;font-size:.85rem;margin-bottom:.3rem">Schedule (Tag/Nacht-Switch)</div>'+
  noteHtml+
  '<div style="display:grid;grid-template-columns:auto 1fr;gap:.4rem;margin-top:.3rem;max-width:560px">'+
  '<label>active</label><input type="checkbox" id="ed-sch-active-'+task+'"'+(active?' checked':'')+'>'+
  '<label>from (HH:MM)</label><input id="ed-sch-from-'+task+'" value="'+esc(fromV)+'" placeholder="22:00">'+
  '<label>to (HH:MM)</label><input id="ed-sch-to-'+task+'" value="'+esc(toV)+'" placeholder="06:00">'+
  '<label>provider</label><select id="ed-sch-prov-'+task+'" onchange="loadScheduleModels(\\''+task+'\\')"><option value="">(keep current)</option>'+provOpts+'</select>'+
  '<label>model</label><select id="ed-sch-model-'+task+'"><option value="'+esc(modelV)+'">'+esc(modelV||'(select provider first)')+'</option></select>'+
  '</div></div>';
}

// #316: Lade Modelle fuer Schedule-Provider (gleiche Logik wie loadModelsForProvider, anderer Dropdown).
async function loadScheduleModels(task){
 const provEl=document.getElementById('ed-sch-prov-'+task);
 const modelEl=document.getElementById('ed-sch-model-'+task);
 if(!provEl||!modelEl)return;
 const provider=provEl.value;
 if(!provider){modelEl.innerHTML='<option value="">(select provider first)</option>';return;}
 modelEl.innerHTML='<option>(loading...)</option>';
 try{
  // #328: bei Schedule gibt es keinen separaten base_url — der Schedule
  // erbt die Verbindung. Bei lokalen Providern muesste der User den
  // base_url separat konfigurieren — momentan greifen wir auf die Editor-URL
  // zurueck (Schedule auf gleichem Endpoint wie Day-Setup).
  const urlEl=document.getElementById('ed-baseurl-'+task);
  const baseUrl=urlEl?urlEl.value.trim():'';
  let url='/api/v1/dashboard/llm/models?provider='+encodeURIComponent(provider);
  if(baseUrl)url+='&base_url='+encodeURIComponent(baseUrl);
  const r=await apiFetch(url);
  const j=await r.json();
  const cache=j.cache||{};window.__modelCache=cache;
  const cacheWarning=cache.needs_refresh?'Cache '+String(cache.status||'veraltet')+' – Modell-/Benchmarkdaten aktualisieren. ':'';
  const models=(j.models||j.data&&j.data.models)||[];
  if(!models.length){modelEl.innerHTML='<option value="">(none)</option>';return;}
  modelEl.innerHTML=models.map(m=>{
   const id=m.model||m.id||'';
   return '<option value="'+esc(id)+'">'+esc(id)+'</option>';
  }).join('');
 }catch(err){modelEl.innerHTML='<option value="">(error)</option>';}
}

// #313: Models-Dropdown dynamisch befuellen + Preise anzeigen.
async function loadModelsForProvider(task,currentModel){
 const provEl=document.getElementById('ed-prov-'+task);
 const modelEl=document.getElementById('ed-model-'+task);
 const noteEl=document.getElementById('ed-modelnote-'+task);
 if(!provEl||!modelEl)return;
 const provider=provEl.value;
 const keepModel=currentModel||modelEl.value;
 const request={};modelEl.__modelRequest=request;
 const isCurrent=()=>document.getElementById('ed-model-'+task)===modelEl&&modelEl.__modelRequest===request;
 const unknownOption=()=>'<option value="'+esc(keepModel)+'" data-assessment="Nicht durch die aktuelle Liste bestätigt; Verfügbarkeit unbekannt">'+esc(keepModel?keepModel+' (nicht bestätigt)':'(keine bestätigte Auswahl)')+'</option>';
 // #328: base_url aus dem Editor-Form mitgeben — das Backend nutzt sie als
 // base_url_override, sonst baut _build_inner mit der Config-Default-URL.
 const urlEl=document.getElementById('ed-baseurl-'+task);
 const baseUrl=urlEl?urlEl.value.trim():'';
 modelEl.innerHTML='<option value="'+esc(keepModel)+'">(loading...)</option>';
 if(noteEl)noteEl.textContent='';
 try{
  const cfg=(window.__llmCfg||[]).find(r=>r.task===task)||{};
  const threshold=(((cfg.model_quality||{}).suitability||{}).threshold);
  const margin=Number(cfg.overqualification_margin_ratio==null?0.2:cfg.overqualification_margin_ratio);
  const costAdvisory=cfg.cost_advisory_enabled!==false;
  let url='/api/v1/dashboard/llm/models?provider='+encodeURIComponent(provider)+'&task='+encodeURIComponent(task);
  if(typeof threshold==='number')url+='&threshold='+encodeURIComponent(String(threshold));
  url+='&margin='+encodeURIComponent(String(margin))+'&cost_advisory='+encodeURIComponent(String(costAdvisory));
  if(baseUrl)url+='&base_url='+encodeURIComponent(baseUrl);
  const r=await apiFetch(url);
  if(r.ok===false)throw new Error('HTTP '+r.status);
  const j=await r.json();
  if(!isCurrent())return;
  const cache=j.cache||{};window.__modelCache=cache;
  const cacheWarning=cache.needs_refresh?'Cache '+String(cache.status||'veraltet')+' – Modell-/Benchmarkdaten aktualisieren. ':'';
  const models=(j.models||j.data&&j.data.models)||[];
  if(!models.length){
   modelEl.innerHTML=unknownOption();
   if(noteEl){
    if(provider==='ollama'||provider==='lmstudio'){
     noteEl.innerHTML='<span style="color:#f59e0b">Endpoint nicht erreichbar oder leer — pruefe URL/Service</span>';
    }else if(provider==='manual'){
     noteEl.textContent='Manual-Provider hat kein Modell-Listing';
    }else{
     noteEl.innerHTML='<span style="color:#f59e0b">Keine Daten — `samuel refresh-pricing` ausfuehren oder OpenRouter-Cache leer</span>';
    }
   }
   return;
  }
  // Build options mit Preis-Annotation
  const keepUnknown=keepModel&&!models.some(m=>(m.model||m.id||'')===keepModel);
  modelEl.innerHTML=(keepUnknown?unknownOption():'')+models.map(m=>{
   const id=m.model||m.id||'';
   const prompt=m.prompt_per_1k||0;
   const completion=m.completion_per_1k||0;
   let price='';
   if(prompt>0||completion>0){
    price=' ($'+prompt.toFixed(4)+'/$'+completion.toFixed(4)+' per 1k)';
   }
   const ctx=m.context_length?' ['+(m.context_length/1000).toFixed(0)+'k ctx]':'';
   const reasoningInfo=m.reasoning_info||{};
   const reasoning=reasoningInfo.is_reasoning?' [Reasoning: ja]':' [Reasoning: nein]';
   const suitability=m.suitability||{};
   let quality='keine Qualitätsdaten für '+String(suitability.index||'diesen Task');
   let bench=' [Qualität: keine Daten]';
   if(suitability.available){
    const score=Number(suitability.score).toFixed(1);
    const limit=Number(suitability.threshold).toFixed(1);
    const verdict=suitability.status==='overqualified'?'überqualifiziert':(suitability.status==='suitable'?'geeignet':'unterqualifiziert');
    quality=String(suitability.index||'Index')+' '+score+' / Schwelle '+limit+' ('+verdict+')';
    bench=' ['+quality+']';
   }
   const advisory=m.cost_advisory||{};const rec=advisory.recommendation||{};
   let costHint='';
   if(advisory.enabled===false)costHint='; optionaler Kostenhinweis deaktiviert';
   else if(advisory.status==='recommendation_available')costHint='; optionaler Kostenhinweis: '+String(rec.model||'Alternative')+' dominiert beide Preisachsen ('+String(rec.candidate_count||1)+' Kandidat(en), Tie-Break Modell-ID)';
   else if(suitability.status==='overqualified')costHint='; kein belegbarer günstigerer Pareto-Kandidat ('+String(advisory.status||'keine Daten')+')';
   const assessment=cacheWarning+(reasoningInfo.is_reasoning?'Reasoning-Modell':'Kein Reasoning-Modell')+'; '+quality+costHint+'; Quelle: '+String(reasoningInfo.source||'unbekannt');
   const sel=id===keepModel?' selected':'';
   return '<option value="'+esc(id)+'" data-assessment="'+esc(assessment)+'"'+sel+'>'+esc(id)+esc(price)+esc(ctx)+esc(reasoning)+esc(bench)+'</option>';
  }).join('');
  updateModelAssessment(task,models.length);
 }catch(err){
  if(!isCurrent())return;
  modelEl.innerHTML=unknownOption();
  if(noteEl)noteEl.innerHTML='<span style="color:#ef4444">Fehler beim Laden: '+esc(String(err))+'</span>';
 }
}

function updateModelAssessment(task,count){
 const modelEl=document.getElementById('ed-model-'+task);
 const noteEl=document.getElementById('ed-modelnote-'+task);
 if(!modelEl||!noteEl)return;
 const selected=modelEl.options[modelEl.selectedIndex];
 const prefix=typeof count==='number'?count+' Modelle · ':'';
 noteEl.textContent=prefix+((selected&&selected.dataset.assessment)||'Keine Bewertungsdaten für die Auswahl');
}

async function refreshModelsForProvider(task){
 const provEl=document.getElementById('ed-prov-'+task);
 if(!provEl)return;
 if(provEl.value==='ollama'||provEl.value==='lmstudio'||provEl.value==='manual'){
  await loadModelsForProvider(task);
  return;
 }
 const noteEl=document.getElementById('ed-modelnote-'+task);
 if(noteEl)noteEl.textContent='OpenRouter-Daten werden aktualisiert …';
 try{
  await refreshOpenRouterCache();
  await loadModelsForProvider(task);
 }catch(err){
  if(noteEl)noteEl.textContent='Aktualisierung fehlgeschlagen: '+String(err);
  showToast('Modell-Daten konnten nicht aktualisiert werden','err');
 }
}

// #312/#328: Bei Provider-Aenderung URL korrekt halten:
// - Initial-Render: bestehende Config-URL beibehalten, nur Note setzen.
// - Bei explizitem Provider-Wechsel durch User: URL IMMER auf den neuen Default
//   setzen (oder leeren bei API-Providern). Die alte URL gehoerte zum alten
//   Provider und ist fuer den neuen definitiv falsch (#328-User-Report).
function onLLMProviderChange(task,initial){
 const provEl=document.getElementById('ed-prov-'+task);
 const urlEl=document.getElementById('ed-baseurl-'+task);
 const noteEl=document.getElementById('ed-urlnote-'+task);
 if(!provEl||!urlEl||!noteEl)return;
 const meta=LLM_PROVIDER_DEFAULTS[provEl.value]||{};
 if(!initial){
  // Provider-Wechsel: URL auf neuen Default oder leer.
  urlEl.value=meta.url||'';
 }
 noteEl.textContent=meta.urlNote||'';
 // Visual-Hint bei Pflicht-URL ohne Wert
 const errEl=document.getElementById('ed-urlerr-'+task);
 if(errEl){
  if(meta.urlRequired&&!urlEl.value.trim()){
   urlEl.style.borderColor='#ef4444';
   errEl.style.display='block';
  }else{
   urlEl.style.borderColor='';
   errEl.style.display='none';
  }
 }
 // #313: bei Provider-Change auch Models neu laden (nicht beim Initial-Render —
 // das macht openLLMTaskEditor() bereits separat).
 if(!initial){
  loadModelsForProvider(task,/*currentModel=*/'');
 }
}

function closeLLMTaskEditor(task){
 const e=document.getElementById('llm-edit-'+task);if(e){e.style.display='none';e.innerHTML='';}
}

async function saveLLMTaskConfig(task){
 const get=id=>{const el=document.getElementById(id);return el?el.value.trim():'';};
 const cfg={};
 const p=get('ed-prov-'+task);if(p)cfg.provider=p;
 const m=get('ed-model-'+task);if(m)cfg.model=m;else cfg.model='';
 const b=get('ed-baseurl-'+task);cfg.base_url=b;
 const t=get('ed-timeout-'+task);if(t)cfg.timeout=Number(t);else cfg.timeout='';
 const sp=get('ed-sp-'+task);cfg.system_prompt=sp;
 // #351 L3: Per-Provider-Map einsammeln. Leere Map -> Backend droppt Field.
 cfg.system_prompt_by_provider=_collectPromptByProvider(task);
 const mx=get('ed-maxt-'+task);if(mx)cfg.max_tokens=Number(mx);else cfg.max_tokens='';
 const rr=get('ed-reason-'+task);if(rr)cfg.reasoning_reserve=Number(rr);else cfg.reasoning_reserve=0;
 const ca=document.getElementById('ed-cost-advisory-'+task);cfg.cost_advisory_enabled=ca?!!ca.checked:true;
 const om=get('ed-overqual-margin-'+task);cfg.overqualification_margin_ratio=om===''?0.2:Number(om);
 const tm=get('ed-temp-'+task);if(tm)cfg.temperature=Number(tm);else cfg.temperature='';
 // #316: Persist a schedule whenever the editor section is present.
 const aEl=document.getElementById('ed-sch-active-'+task);
 if(aEl){
  const sched={
   active:!!aEl.checked,
   from:get('ed-sch-from-'+task),
   to:get('ed-sch-to-'+task),
   provider:get('ed-sch-prov-'+task),
   model:get('ed-sch-model-'+task)
  };
  cfg.schedule=sched;
 }
 try{
  const r=await apiFetch('/api/v1/settings/llm/task',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task:task,config:cfg})});
  const j=await r.json();const d=j.data||j;
  if(r.ok&&d.updated){
   showToast('Saved: '+task+(d.restart_required?' — Agent-Neustart erforderlich':''),d.restart_required?'warn':'ok');
   closeLLMTaskEditor(task);
   await loadSettings();
  }else{
   showToast('Fehler: '+(d.error||JSON.stringify(d)),'err');
  }
 }catch(err){showToast('Netzwerk-Fehler: '+err,'err');}
}

async function saveLLMGlobalConfig(){
 const providerEl=document.getElementById('set-llm-default');
 const fallbackEl=document.getElementById('set-llm-fallbacks');
 if(!providerEl||!fallbackEl)return;
 const fallbacks=fallbackEl.value.split(',').map(value=>value.trim()).filter(Boolean);
 try{
  const response=await apiFetch('/api/v1/settings/llm/global',{
   method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({provider:providerEl.value,fallbacks:fallbacks})
  });
  const body=await response.json();const data=body.data||body;
  if(response.ok&&data.updated){
   showToast('Default/Fallback gespeichert — Agent-Neustart erforderlich'+(data.environment_override?' (SAMUEL_LLM_PROVIDER überschreibt weiterhin)':''),'warn');
   await loadSettings();
  }else{showToast('Fehler: '+(data.error||JSON.stringify(data)),'err');}
 }catch(err){showToast('Netzwerk-Fehler: '+err,'err');}
}

// #314: Test-Connection — POST aktuelle Form-Werte gegen /test-connection,
// Result als Badge unter dem Button.
async function testLLMConnection(task){
 const get=id=>{const el=document.getElementById(id);return el?el.value.trim():'';};
 const provider=get('ed-prov-'+task);
 const cfg={};
 const m=get('ed-model-'+task);if(m)cfg.model=m;
 const b=get('ed-baseurl-'+task);if(b)cfg.base_url=b;
 const t=get('ed-timeout-'+task);if(t)cfg.timeout=Number(t);
 const btn=document.getElementById('ed-testbtn-'+task);
 const out=document.getElementById('ed-testresult-'+task);
 if(!provider){if(out){out.style.display='block';out.innerHTML='<span style="color:#ef4444">Provider erforderlich</span>';}return;}
 if(btn){btn.disabled=true;btn.textContent='Testing...';}
 if(out){out.style.display='block';out.innerHTML='<span style="color:#94a3b8">Pruefe '+esc(provider)+'...</span>';}
 try{
  const r=await apiFetch('/api/v1/dashboard/llm/test-connection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider:provider,config:cfg})});
  const j=await r.json();const d=j.data||j;
  if(out){
   if(d.valid){
    let msg='<span style="color:#10b981;font-weight:600">&#10004; Connection OK</span>';
    if(d.detail)msg+=' <span style="color:#64748b">('+esc(d.detail)+')</span>';
    if(d.balance!==undefined&&d.balance!==null){
     msg+=' <span style="color:#10b981;font-weight:600;margin-left:.5rem">Balance: $'+Number(d.balance).toFixed(4)+'</span>';
    }
    out.innerHTML=msg;
   }else{
    out.innerHTML='<span style="color:#ef4444;font-weight:600">&#10006; Connection failed: '+esc(d.detail||'unknown')+'</span>';
   }
  }
 }catch(err){
  if(out)out.innerHTML='<span style="color:#ef4444">Netzwerk-Fehler: '+esc(String(err))+'</span>';
 }finally{
  if(btn){btn.disabled=false;btn.textContent='Test';}
 }
}

// #315/#338/#357: System-prompts view and authenticated edit modal.
// Per-Provider-Zuweisung erfolgt seit #357 ausschliesslich ueber den Task-Editor
// (system_prompt_by_provider-Map, #351). Modal-Save schreibt immer in
// config/llm/prompts/<name> (Library); die backend-seitige Cascade auf
// provider/<X>/<file>.md bzw. model/<Y>/<file>.md bleibt funktional als
// Backward-Compat fuer existierende Files, wird aber vom UI nicht mehr
// adressiert.
function _llmPromptsModal(){
 let m=document.getElementById('prompt-modal');
 if(m)return m;
 m=document.createElement('div');
 m.id='prompt-modal';
 m.style.cssText='display:none;position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:9999;align-items:center;justify-content:center';
 m.innerHTML='<div style="background:#0f172a;border:1px solid #334155;border-radius:6px;width:80vw;max-width:900px;height:80vh;display:flex;flex-direction:column;padding:1rem">'+
  '<div id="pm-title" style="font-weight:700;font-size:1rem;margin-bottom:.5rem;color:#e2e8f0"></div>'+
  // #351 L2: optionaler eigener Name fuer "Save as ..." — wenn gefuellt
  // landet die Datei unter dem neuen Namen in der Library statt den
  // Original-Filename zu ueberschreiben.
  '<div id="pm-saveas-row" style="display:none;font-size:.75rem;margin-bottom:.4rem;color:#94a3b8;align-items:center;gap:.4rem">'+
   '<span>Save as (optional, eigener Name):</span>'+
   '<input id="pm-saveas" type="text" placeholder="z.B. mein_planner.md" style="flex:1;background:#020617;color:#e2e8f0;border:1px solid #334155;border-radius:4px;padding:.2rem .4rem;font-size:.75rem">'+
   '<span style="color:#64748b;font-size:.7rem">leer = Original-Name &uuml;berschreiben</span>'+
  '</div>'+
  '<div id="pm-source" style="font-size:.75rem;color:#94a3b8;margin-bottom:.5rem"></div>'+
  '<textarea id="pm-content" style="flex:1;background:#020617;color:#e2e8f0;border:1px solid #334155;border-radius:4px;padding:.5rem;font-family:monospace;font-size:.8rem;resize:none;overflow-y:auto"></textarea>'+
  '<div id="pm-error" style="color:#ef4444;font-size:.8rem;margin-top:.4rem;display:none"></div>'+
  '<div style="margin-top:.6rem;display:flex;gap:.5rem;justify-content:flex-end">'+
  '<button id="pm-reset" onclick="resetPromptToDefault()" style="display:none;background:#f59e0b;color:#0f172a;border:none;padding:.4rem 1rem;border-radius:4px;cursor:pointer;font-weight:600" title="Reset to Default — Operator-Override loeschen, Lookup faellt auf naechsthoehere Stufe zurueck">Reset to Default</button>'+
  '<button id="pm-save" onclick="savePromptModal()" style="display:none;background:#10b981;color:#0f172a;border:none;padding:.4rem 1rem;border-radius:4px;cursor:pointer;font-weight:600">Save</button>'+
  '<button onclick="closePromptModal()" style="background:#475569;color:#fff;border:none;padding:.4rem 1rem;border-radius:4px;cursor:pointer">Close</button>'+
  '</div></div>';
 document.body.appendChild(m);
 return m;
}

// #357: Modal arbeitet ausschliesslich auf Library-Files (config/llm/prompts/<name>).
// Laedt aktuellen Inhalt + Source-Indikator und schaltet den Reset-Button
// abhaengig davon, ob ein operator-generic-Override existiert.
async function _refreshPromptModalContent(){
 const ta=document.getElementById('pm-content');
 const name=ta.dataset.promptName||'';
 if(!name)return;
 try{
  const r=await apiFetch('/api/v1/dashboard/llm/prompts/'+encodeURIComponent(name));
  const j=await r.json();const d=j.data||j;
  ta.value=d.content||'';
  const src=d.source||{};
  const path=src.path||'(nicht vorhanden)';
  document.getElementById('pm-source').innerHTML='Aktuell aktiv: '+esc(src.source||'package')+' &mdash; '+esc(path);
  const resetBtn=document.getElementById('pm-reset');
  if(resetBtn){
   const isOperatorOverride=src.source==='operator-generic';
   resetBtn.style.display=isOperatorOverride?'inline-block':'none';
  }
 }catch(err){
  document.getElementById('pm-source').textContent='Netzwerk-Fehler: '+err;
 }
}

async function resetPromptToDefault(){
 const ta=document.getElementById('pm-content');
 const name=ta.dataset.promptName||'';
 if(!name)return;
 if(!confirm('Operator-Override fuer "'+name+'" loeschen?\\n\\nDer Lookup faellt damit auf den Package-Default zurueck.'))return;
 try{
  const r=await apiFetch('/api/v1/dashboard/llm/prompts/'+encodeURIComponent(name),{method:'DELETE'});
  const j=await r.json();const d=j.data||j;
  if(r.ok&&d.deleted){
   showToast('Override geloescht: '+name,'ok');
   _refreshPromptModalContent();
  }else{
   const errEl=document.getElementById('pm-error');
   errEl.textContent='Fehler: '+(d.error||d.reason||JSON.stringify(d));
   errEl.style.display='block';
  }
 }catch(err){
  const errEl=document.getElementById('pm-error');
  errEl.textContent='Netzwerk-Fehler: '+err;
  errEl.style.display='block';
 }
}

async function viewSystemPrompt(task){
 const sel=document.getElementById('ed-sp-'+task);
 const name=sel?sel.value.trim():'';
 if(!name){showToast('Kein Prompt ausgewaehlt','warn');return;}
 const m=_llmPromptsModal();
 document.getElementById('pm-title').textContent='View: '+name;
 document.getElementById('pm-source').textContent='Lade...';
 document.getElementById('pm-content').value='';
 document.getElementById('pm-content').readOnly=true;
 document.getElementById('pm-save').style.display='none';
 document.getElementById('pm-error').style.display='none';
 // #351 L2: Save-as-Row im View-Mode versteckt
 const saveAsRow=document.getElementById('pm-saveas-row');
 if(saveAsRow)saveAsRow.style.display='none';
 m.style.display='flex';
 try{
  const r=await apiFetch('/api/v1/dashboard/llm/prompts/'+encodeURIComponent(name));
  const j=await r.json();const d=j.data||j;
  if(r.ok&&d.content){
   document.getElementById('pm-content').value=d.content;
   document.getElementById('pm-source').textContent='Read-only ('+(d.content.length)+' chars)';
  }else{
   document.getElementById('pm-source').textContent='Fehler: '+(d.error||'Prompt nicht gefunden');
  }
 }catch(err){
  document.getElementById('pm-source').textContent='Netzwerk-Fehler: '+err;
 }
}

async function editSystemPrompt(task){
 const sel=document.getElementById('ed-sp-'+task);
 const name=sel?sel.value.trim():'';
 if(!name){showToast('Kein Prompt ausgewaehlt','warn');return;}
 const m=_llmPromptsModal();
 document.getElementById('pm-title').textContent='Edit: '+name;
 document.getElementById('pm-source').textContent='Lade...';
 document.getElementById('pm-content').value='';
 document.getElementById('pm-content').readOnly=false;
 const ta=document.getElementById('pm-content');
 ta.dataset.promptName=name;
 document.getElementById('pm-save').style.display='inline-block';
 document.getElementById('pm-error').style.display='none';
 // #351 L2: Save-as-Input nur im Edit-Mode anzeigen + leer initialisieren
 const saveAsRow=document.getElementById('pm-saveas-row');
 if(saveAsRow)saveAsRow.style.display='flex';
 const saveAsInput=document.getElementById('pm-saveas');
 if(saveAsInput)saveAsInput.value='';
 m.style.display='flex';
 _refreshPromptModalContent();
}

async function savePromptModal(){
 const ta=document.getElementById('pm-content');
 const origName=ta.dataset.promptName||'';
 const content=ta.value;
 const errEl=document.getElementById('pm-error');
 errEl.style.display='none';
 if(!origName){errEl.textContent='Kein Name gesetzt';errEl.style.display='block';return;}
 if(!content.trim()){errEl.textContent='Inhalt darf nicht leer sein';errEl.style.display='block';return;}
 // #351 L2: optionaler eigener Name. Wenn gesetzt -> speichert als
 // <eigener_name>.md in der Library statt das Original zu ueberschreiben.
 const saveAsEl=document.getElementById('pm-saveas');
 const saveAs=saveAsEl?saveAsEl.value.trim():'';
 let targetName=origName;
 if(saveAs){
  // Frontend-seitige Sanity-Pruefung; Backend validiert nochmal hart.
  // (Backslash via charCodeAt damit der Python-f-string nicht mit
  // backslash-escapes brechen kann, siehe Memory feedback_dashboard_js_escapes.)
  let hasBack=false;for(let i=0;i<saveAs.length;i++){if(saveAs.charCodeAt(i)===92){hasBack=true;break;}}
  if(saveAs.indexOf('/')>=0||hasBack||saveAs.indexOf('..')>=0){
   errEl.textContent='Save-as Name darf keine Pfad-Separatoren oder ".." enthalten';
   errEl.style.display='block';return;
  }
  targetName=saveAs.endsWith('.md')?saveAs:(saveAs+'.md');
 }
 try{
  // #357: kein scope mehr — Modal-Save schreibt immer in die Library
  // (config/llm/prompts/<name>). Per-Provider-Zuweisung erfolgt ueber den
  // Task-Editor (system_prompt_by_provider, #351).
  const r=await apiFetch('/api/v1/dashboard/llm/prompts/'+encodeURIComponent(targetName),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:content})});
  const j=await r.json();const d=j.data||j;
  if(r.ok&&d.saved){
   showToast('Prompt gespeichert: '+targetName,'ok');
   // Wenn unter neuem Namen gespeichert: Modal-Inhalt auf neuen Namen umstellen
   // damit weitere Edits an der neuen Datei landen.
   if(saveAs){ta.dataset.promptName=targetName;document.getElementById('pm-title').textContent='Edit: '+targetName;saveAsEl.value='';}
   _refreshPromptModalContent();
   // #351-fix: refresh aller Task-system_prompt-Dropdowns + Per-Provider-
   // Selects, damit die neue Library-Datei sofort waehlbar ist (vorher
   // erforderte das einen kompletten Editor-Reload).
   ['planning','implementation','review','healing','evaluation','default'].forEach(t=>{
    const s=document.getElementById('ed-sp-'+t);
    if(s)loadPromptsForTask(t,s.value);
   });
  }else{
   errEl.textContent='Fehler: '+(d.error||JSON.stringify(d));
   errEl.style.display='block';
  }
 }catch(err){
  errEl.textContent='Netzwerk-Fehler: '+err;
  errEl.style.display='block';
 }
}

function closePromptModal(){
 const m=document.getElementById('prompt-modal');
 if(m)m.style.display='none';
 const saveAsRow=document.getElementById('pm-saveas-row');
 if(saveAsRow)saveAsRow.style.display='none';
 const resetBtn=document.getElementById('pm-reset');
 if(resetBtn)resetBtn.style.display='none';
}

async function syncLabels(){
 const btn=document.getElementById('btn-sync-labels');
 const out=document.getElementById('labels-result');
 btn.disabled=true;out.textContent='Synchronisiere...';
 try{
  const r=await apiFetch('/api/v1/setup/labels',{method:'POST',headers:{'Content-Type':'application/json'}});
  const j=await r.json();
  const d=j.data||j;
  if(r.ok&&d.synced!==false){
   const c=(d.created||[]).length,s=(d.skipped||[]).length,e=(d.errors||[]).length;
   out.textContent='Created='+c+', Skipped='+s+', Errors='+e;
   showToast('Labels synchronisiert: +'+c+' / skip '+s+(e?' / err '+e:''), e?'warn':'ok');
  }else{
   const msg=d.error||d.errors||JSON.stringify(d);
   out.textContent='Fehler: '+msg;
   showToast('Fehler beim Sync: '+msg,'err');
  }
 }catch(err){out.textContent='Fehler: '+err;showToast('Netzwerk-Fehler: '+err,'err');}
 finally{btn.disabled=false;}
}

async function loadSelfCheck(){
 const d=await apiFetch('/api/v1/dashboard/self_check').then(r=>r.json());
 const data=d.data||d;
 document.getElementById('sc-mode').textContent=data.mode||'-';
 const h=!!data.healthy;const el=document.getElementById('sc-healthy');
 el.textContent=h?'OK':'Fehler';el.className='val '+(h?'ok':'err');
 const readiness=(data.operational_readiness||{}).status||'unknown';
 const readinessEl=document.getElementById('sc-readiness');readinessEl.textContent=readiness;readinessEl.className='val '+(readiness==='ready'?'ok':readiness==='blocked'?'err':'warn');
 const qualification=(data.qualification||{}).status||'not_checked';
 const qualificationEl=document.getElementById('sc-qualification');qualificationEl.textContent=qualification;qualificationEl.className='val '+(qualification==='passed'?'ok':qualification==='failed'?'err':'warn');
 const tb=document.getElementById('sc-body');tb.innerHTML='';
 const checks=data.checks||[];
 if(checks.length){checks.forEach(c=>{const cls=c.status==='OK'?'ok':'err';
  tb.innerHTML+='<tr><td>'+esc(c.name||'-')+'</td><td class="'+cls+'">'+esc(c.status||'-')+'</td><td>'+esc(c.time||'-')+'</td><td>'+esc(c.detail||'-')+'</td></tr>';});}
 else{tb.innerHTML='<tr><td colspan="4" class="empty">Keine Self-Check-Daten</td></tr>';}
}

setInterval(()=>{
 if(!autoRefresh){document.getElementById('countdown').textContent='-';return;}
 cd--;document.getElementById('countdown').textContent=cd;
 if(cd<=0){cd=REFRESH_INTERVAL;loadTabData(currentTab)}
},1000);
document.getElementById('auto-refresh-btn').textContent='auto-refresh: '+(autoRefresh?'on':'off');
applyTheme(document.documentElement.dataset.theme);
showTab(currentTab);
checkFirstRun();
</script>
</body>
</html>
"""


def render_dashboard_html(product_version: str | None = None, *, timezone: str = "UTC") -> str:
    """Render the public shell with the canonical product version visible.

    Build revision and dirty state stay on the authenticated status path.  The
    browser still refreshes all build fields after authentication, but a
    failed or not-yet-completed API load can no longer erase the product
    version from the initial operator-visible surface.
    """

    visible_version = str(product_version or "0+unknown")
    return DASHBOARD_HTML.replace(
        _PRODUCT_VERSION_MARKER,
        escape_html(visible_version, quote=True),
        1,
    ).replace(
        'data-timezone="UTC"',
        f'data-timezone="{escape_html(timezone, quote=True)}"',
        1,
    )


class SAMUELRequestHandler(BaseHTTPRequestHandler):
    rest_api: RestAPI
    webhook_adapter: WebhookIngressAdapter
    dashboard: DashboardHandler
    setup_handler: SetupHandler
    auth_middleware: DashboardAuth | None = None
    auth_actor: AuthenticatedActor | None = None

    def log_message(self, format: str, *args: Any) -> None:
        log.debug(format, *args)

    def _send_json(
        self, status: int, data: Any, *, headers: list[tuple[str, str]] | None = None
    ) -> None:
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in headers or []:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            self._raw_request_body = b""
            return {}
        raw = self.rfile.read(length)
        self._raw_request_body = raw
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}

    # Paths that are reachable without API-key auth even when auth is enabled.
    # Webhook uses HMAC, not API key. Everything else (including the HTML
    # dashboard) requires the key when SAMUEL_API_KEY is set.
    # #402: Die HTML-Shell (/ und /dashboard) ist auth-frei, damit der Browser
    # die Seite ueberhaupt laden kann; alle DATEN kommen ueber /api/* und bleiben
    # geschuetzt. Das JS fragt bei einem 401 einmal nach dem API-Key. Webhook
    # ist signatur-validiert (eigener Pfad).
    _AUTH_EXEMPT_ROUTES: set[tuple[str, str]] = {
        ("POST", "/api/v1/webhook"),
        ("POST", "/api/v1/auth/login"),
        ("GET", "/api/v1/auth/mode"),
        ("HEAD", "/api/v1/auth/mode"),
        ("GET", "/"),
        ("HEAD", "/"),
        ("GET", "/dashboard"),
        ("HEAD", "/dashboard"),
    }

    def _authorize_current(self) -> bool:
        """Authenticate and authorize the concrete endpoint before dispatch."""

        auth = getattr(self.__class__, "auth_middleware", None)
        if auth is None:
            self.auth_actor = None
            return True
        route = (self.command.upper(), urlsplit(self.path).path)
        if route in self._AUTH_EXEMPT_ROUTES:
            self.auth_actor = None
            return True
        decision = auth.authorize(self.command, self.path, dict(self.headers))
        self.auth_actor = decision.actor
        if decision.allowed:
            return True
        self._send_json(
            decision.status,
            {
                "error": "unauthorized" if decision.status == 401 else "forbidden",
                "code": decision.code,
            },
        )
        return False

    @staticmethod
    def _principal_payload(principal: Any) -> dict[str, Any]:
        return {
            "principal_id": principal.principal_id,
            "username": principal.username,
            "kind": principal.kind,
            "disabled": principal.disabled,
            "roles": list(principal.roles),
            "created_at": principal.created_at.isoformat(),
            "updated_at": principal.updated_at.isoformat(),
        }

    def _local_auth(self) -> LocalIdentityService | None:
        auth = getattr(self.__class__, "auth_middleware", None)
        return auth.local if auth is not None else None

    def _session_cookie_headers(self, session_token: str, csrf_token: str) -> list[tuple[str, str]]:
        auth = getattr(self.__class__, "auth_middleware", None)
        if auth is None:
            return []
        secure = "; Secure" if auth.config.secure_cookies else ""
        maximum = auth.config.session_absolute_seconds
        return [
            (
                "Set-Cookie",
                f"{auth.cookie_name}={session_token}; Path=/; HttpOnly; SameSite=Strict; "
                f"Max-Age={maximum}{secure}",
            ),
            (
                "Set-Cookie",
                f"samuel_csrf={csrf_token}; Path=/; SameSite=Strict; Max-Age={maximum}{secure}",
            ),
        ]

    def _clear_session_cookie_headers(self) -> list[tuple[str, str]]:
        auth = getattr(self.__class__, "auth_middleware", None)
        secure = "; Secure" if auth is not None and auth.config.secure_cookies else ""
        cookie_name = auth.cookie_name if auth is not None else "samuel_session"
        return [
            (
                "Set-Cookie",
                f"{cookie_name}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0{secure}",
            ),
            ("Set-Cookie", f"samuel_csrf=; Path=/; SameSite=Strict; Max-Age=0{secure}"),
        ]

    def _fresh_administrator_required(self) -> bool:
        local = self._local_auth()
        actor = self.auth_actor
        if local is None or actor is None:
            self._send_json(409, {"error": "local identity mode required"})
            return False
        if not local.is_fresh(actor):
            self._send_json(
                403,
                {"error": "forbidden", "code": "fresh_reauthentication_required"},
            )
            return False
        return True

    def _send_identity_error(self, exc: IdentityError) -> None:
        status = 400
        if exc.code in {"authentication_failed", "reauthentication_failed"}:
            status = 401
        elif exc.code == "authentication_rate_limited":
            status = 429
        elif exc.code in {
            "identity_username_conflict",
            "identity_last_administrator",
            "identity_not_active",
            "identity_recovery_not_pending",
        }:
            status = 409
        self._send_json(status, {"error": str(exc), "code": exc.code})

    def _actor_payload(self) -> dict[str, Any]:
        actor = self.auth_actor
        if actor is None:
            return {}
        return {
            "principal_id": actor.principal_id,
            "username": actor.username,
            "kind": actor.kind,
            "roles": list(actor.roles),
            "permissions": sorted(actor.permissions),
            "authentication": actor.authentication,
        }

    @staticmethod
    def _session_payload(session: Any) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "principal_id": session.principal_id,
            "created_at": session.created_at.isoformat(),
            "authenticated_at": session.authenticated_at.isoformat(),
            "last_seen_at": session.last_seen_at.isoformat(),
            "expires_at": session.expires_at.isoformat(),
            "revoked_at": session.revoked_at.isoformat() if session.revoked_at else None,
            "revoked_by": session.revoked_by,
        }

    def _setup_access_allowed(self) -> bool:
        """Allow setup via existing auth, or locally during the first run."""

        if getattr(self.__class__, "auth_middleware", None) is not None:
            return True
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except (ValueError, IndexError):
            return False

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/dashboard":
            self._send_html(
                render_dashboard_html(
                    __build_info__.product_version, timezone=self.dashboard.get_display_timezone()
                )
            )
            return

        if urlsplit(self.path).path == "/api/v1/auth/mode":
            auth = getattr(self.__class__, "auth_middleware", None)
            self._send_json(
                200,
                auth.status()
                if auth is not None
                else {
                    "access_mode": "disabled",
                    "secure_cookies": False,
                    "transport": "test_only",
                    "identity_status": "disabled",
                    "legacy_fallback": False,
                },
            )
            return

        if not self._authorize_current():
            return

        if self.path == "/api/v1/auth/check":
            self._send_json(
                200,
                {
                    "authenticated": True,
                    "auth_required": self.auth_middleware is not None,
                },
            )
            return

        if self.path == "/api/v1/auth/session":
            self._send_json(200, {"actor": self._actor_payload()})
            return

        if self.path == "/api/v1/admin/users":
            local = self._local_auth()
            if local is None:
                self._send_json(409, {"error": "local identity is unavailable"})
                return
            self._send_json(
                200, {"users": [self._principal_payload(row) for row in local.list_principals()]}
            )
            return

        if self.path.startswith("/api/v1/admin/sessions"):
            local = self._local_auth()
            if local is None:
                self._send_json(409, {"error": "local identity is unavailable"})
                return
            from urllib.parse import parse_qs

            query = parse_qs(urlsplit(self.path).query)
            principal_values = query.get("principal_id")
            principal_id = principal_values[0] if principal_values else None
            self._send_json(
                200,
                {
                    "sessions": [
                        self._session_payload(row) for row in local.list_sessions(principal_id)
                    ]
                },
            )
            return

        if self.path == "/api/v1/admin/tokens":
            local = self._local_auth()
            if local is None:
                self._send_json(409, {"error": "local identity is unavailable"})
                return
            principals = {
                principal.principal_id: principal for principal in local.list_principals()
            }
            self._send_json(
                200,
                {
                    "tokens": [
                        {
                            "token_id": token.token_id,
                            "principal_id": token.principal_id,
                            "username": (
                                principals[token.principal_id].username
                                if token.principal_id in principals
                                else "unknown"
                            ),
                            "permissions": list(token.permissions),
                            "created_at": token.created_at.isoformat(),
                            "expires_at": token.expires_at.isoformat(),
                            "revoked_at": (
                                token.revoked_at.isoformat() if token.revoked_at else None
                            ),
                        }
                        for token in local.list_automation_tokens()
                    ]
                },
            )
            return

        if self.path == "/api/v1/setup/status":
            if not self._setup_access_allowed():
                self._send_json(403, {"error": "setup is restricted to localhost"})
                return
            self._send_json(200, self.setup_handler.dashboard_status())
            return

        if self.path == "/api/v1/dashboard/status":
            if self.auth_actor is not None and self.auth_actor.authentication != "legacy_api_key":
                self._send_json(200, self.dashboard.get_viewer_status())
            else:
                self._send_json(200, self.dashboard.get_status())
            return

        if self.path == "/api/v1/dashboard/metrics":
            self._send_json(200, self.dashboard.get_metrics())
            return

        if self.path == "/api/v1/dashboard/transfer_warnings":
            self._send_json(200, {"transfer_warnings": self.dashboard.get_transfer_warnings()})
            return

        if self.path == "/api/v1/dashboard/health":
            self._send_json(200, self.dashboard.get_health())
            return

        if self.path == "/api/v1/dashboard/logs":
            self._send_json(200, self.dashboard.get_logs())
            return

        if self.path == "/api/v1/dashboard/problems":
            self._send_json(200, self.dashboard.get_problems())
            return

        if self.path == "/api/v1/dashboard/security":
            self._send_json(200, self.dashboard.get_security())
            return

        if self.path == "/api/v1/dashboard/compliance/legend":
            # #252: OWASP Top-10 Agentic AI + EU AI Act Artikel-Erklärungen
            self._send_json(200, self.dashboard.get_compliance_legend())
            return

        if self.path == "/api/v1/dashboard/dlq":
            # #334: Dead-Letter-Queue (read-only; Replay via CLI)
            self._send_json(200, self.dashboard.get_dlq())
            return

        if self.path == "/api/v1/dashboard/workflow":
            self._send_json(200, self.dashboard.get_workflow())
            return

        if self.path.startswith("/api/v1/dashboard/workflow/"):
            tail = self.path[len("/api/v1/dashboard/workflow/") :]
            try:
                issue_num = int(tail.split("/", 1)[0])
            except ValueError:
                self._send_json(400, {"error": "invalid issue number"})
                return
            detail = self.dashboard.get_workflow_detail(issue_num)
            if "error" in detail:
                self._send_json(404, detail)
                return
            self._send_json(200, detail)
            return

        if self.path == "/api/v1/dashboard/llm":
            self._send_json(200, self.dashboard.get_llm())
            return

        if self.path == "/api/v1/dashboard/quality":
            self._send_json(200, self.dashboard.get_quality())
            return

        if self.path == "/api/v1/dashboard/activity":
            self._send_json(200, self.dashboard.get_activity())
            return

        if self.path == "/api/v1/dashboard/llm/schedule":
            from samuel.slices.dashboard.data import get_llm_routing_schedule

            cfg = getattr(self.dashboard, "_config", None)
            cdir = "config"
            if cfg is not None:
                try:
                    cdir = str(cfg.get("agent.config_dir", "config"))
                except Exception as exc:  # noqa: BLE001
                    log.warning("Dashboard config_dir lookup failed: %s", exc)
            self._send_json(200, get_llm_routing_schedule(cfg, config_dir=cdir))
            return

        # #311: OpenRouter-Models + Cache-Info
        if self.path.startswith("/api/v1/dashboard/llm/models"):
            from urllib.parse import parse_qs, urlparse

            from samuel.adapters.llm.costs import (
                get_model_cost_advisory,
                get_model_reasoning_info,
                get_model_suitability,
                get_models_for_provider,
            )

            qs = parse_qs(urlparse(self.path).query)
            provider = (qs.get("provider") or [""])[0].lower()
            task = (qs.get("task") or [""])[0].strip()
            try:
                threshold = float((qs.get("threshold") or ["50"])[0])
                margin_ratio = float((qs.get("margin") or ["0.2"])[0])
            except (TypeError, ValueError):
                self._send_json(400, {"error": "threshold and margin must be numeric"})
                return
            if not 0 <= threshold <= 100:
                self._send_json(400, {"error": "threshold must be between 0 and 100"})
                return
            if not 0 <= margin_ratio <= 1:
                self._send_json(400, {"error": "margin must be between 0 and 1"})
                return
            advisory_raw = (qs.get("cost_advisory") or ["true"])[0].lower()
            if advisory_raw not in {"true", "false"}:
                self._send_json(400, {"error": "cost_advisory must be true or false"})
                return
            advisory_enabled = advisory_raw == "true"
            # #328: base_url-Query-Param — der Editor zeigt vielleicht eine andere
            # URL als die Config (z.B. LMStudio auf Remote-Host). Ohne Override
            # baut der Adapter mit der Default-URL und kann die Modelle nicht laden.
            base_url_q = (qs.get("base_url") or [""])[0].strip()
            if not provider:
                self._send_json(400, {"error": "provider query param required"})
                return
            # API-Provider: OpenRouter-Cache. Local: temporary adapter.list_models()
            if provider in ("ollama", "lmstudio", "manual"):
                try:
                    from unittest.mock import MagicMock

                    from samuel.adapters.llm.factory import _build_inner

                    cfg = getattr(self.dashboard, "_config", None)
                    if cfg is None:
                        self._send_json(200, {"provider": provider, "models": []})
                        return
                    secrets_stub = MagicMock()
                    secrets_stub.get.side_effect = lambda k: ""
                    adapter = _build_inner(
                        provider,
                        cfg,
                        secrets_stub,
                        base_url_override=base_url_q or None,
                    )
                    models = adapter.list_models() if hasattr(adapter, "list_models") else []
                except Exception as exc:
                    log.warning("list_models for %s failed: %s", provider, exc)
                    models = []
            else:
                models = get_models_for_provider(provider)
            if task:
                annotated_models = []
                for raw_model in models:
                    row = dict(raw_model)
                    model_id = str(row.get("model") or row.get("id") or "")
                    row["reasoning_info"] = get_model_reasoning_info(model_id)
                    row["suitability"] = get_model_suitability(
                        model_id,
                        task,
                        threshold=threshold,
                        overqualification_margin_ratio=margin_ratio,
                    )
                    row["cost_advisory"] = (
                        get_model_cost_advisory(
                            model_id,
                            task,
                            threshold=threshold,
                            overqualification_margin_ratio=margin_ratio,
                            enabled=advisory_enabled,
                        )
                        if provider == "openrouter"
                        else {
                            "enabled": advisory_enabled,
                            "status": "incomparable_provider",
                            "recommendation": None,
                        }
                    )
                    annotated_models.append(row)
                models = annotated_models
            from samuel.adapters.llm.costs import get_pricing_info

            self._send_json(
                200,
                {"provider": provider, "models": models, "cache": get_pricing_info()},
            )
            return

        if self.path == "/api/v1/dashboard/llm/pricing-info":
            from samuel.adapters.llm.costs import get_pricing_info

            self._send_json(200, get_pricing_info())
            return

        # #315/#338: Prompts-View (free) — list + read
        if self.path.startswith("/api/v1/dashboard/llm/prompts"):
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            scope_values = qs.get("scope")
            scope_param = scope_values[0] if scope_values else None
            cdir = "config"
            cfg = getattr(self.dashboard, "_config", None)
            if cfg is not None:
                try:
                    cdir = str(cfg.get("agent.config_dir", "config"))
                except Exception as exc:  # noqa: BLE001
                    log.warning("Dashboard config_dir lookup failed: %s", exc)

            if parsed.path == "/api/v1/dashboard/llm/prompts":
                from samuel.adapters.llm.prompts import list_available_prompts

                self._send_json(
                    200,
                    {
                        "prompts": list_available_prompts(cdir, scope=scope_param),
                        "scope": scope_param or "generic",
                    },
                )
                return

            if parsed.path.startswith("/api/v1/dashboard/llm/prompts/"):
                from samuel.adapters.llm.prompts import (
                    load_prompt_at_scope,
                    load_system_prompt,
                    resolve_prompt_source,
                )

                name = parsed.path[len("/api/v1/dashboard/llm/prompts/") :]
                if not name or "/" in name or "\\" in name or ".." in name:
                    self._send_json(400, {"error": "invalid prompt name"})
                    return
                # When scope is given, load only that specific override (no
                # cascade fallback) so the modal shows what is actually
                # written there. Otherwise: legacy cascade load.
                if scope_param:
                    content = load_prompt_at_scope(name, cdir, scope=scope_param)
                    src_info = resolve_prompt_source(name, cdir, scope=scope_param)
                    self._send_json(
                        200,
                        {
                            "name": name,
                            "content": content,  # may be empty when no override at this scope
                            "scope": scope_param,
                            "source": src_info,
                        },
                    )
                    return
                content = load_system_prompt(name, cdir)
                if not content:
                    self._send_json(404, {"error": f"prompt not found: {name}"})
                    return
                src_info = resolve_prompt_source(name, cdir)
                self._send_json(
                    200,
                    {
                        "name": name,
                        "content": content,
                        "source": src_info,
                    },
                )
                return

        if self.path == "/api/v1/dashboard/settings":
            self._send_json(200, self.dashboard.get_settings())
            return

        if self.path == "/api/v1/dashboard/self_check":
            self._send_json(200, self.dashboard.get_self_check())
            return

        # #319: Self-Mode-Health (Hang-Patterns, Erfolgsquote)
        if self.path == "/api/v1/dashboard/self-mode/health":
            self._send_json(200, self.dashboard.get_self_mode_health())
            return

        resp = self.rest_api.handle_request("GET", self.path, headers=dict(self.headers))
        self._send_json(resp.get("status", 200), resp.get("data", resp))

    def do_HEAD(self) -> None:  # noqa: N802
        if not self._authorize_current():
            return
        # Minimal HEAD: say 200 for known GET-paths, else 404
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_POST(self) -> None:
        if self.path == "/api/v1/setup/configure":
            content_type = self.headers.get("Content-Type", "").partition(";")[0].strip().lower()
            if content_type != "application/json":
                self._send_json(415, {"error": "application/json required"})
                return
            try:
                if int(self.headers.get("Content-Length", "0")) > 65_536:
                    self._send_json(413, {"error": "setup request too large"})
                    return
            except ValueError:
                self._send_json(400, {"error": "invalid content length"})
                return

        body = self._read_body()

        if self.path == "/api/v1/auth/login":
            local = self._local_auth()
            auth = getattr(self.__class__, "auth_middleware", None)
            if auth is None or auth.config.access_mode != "local_identity" or local is None:
                self._send_json(409, {"error": "local identity login is not active"})
                return
            try:
                issued = local.login(
                    str(body.get("username", "")),
                    str(body.get("password", "")),
                    client_key=str(self.client_address[0]),
                )
            except IdentityError as exc:
                self._send_identity_error(exc)
                return
            self.auth_actor = issued.actor
            self._send_json(
                200,
                {"authenticated": True, "actor": self._actor_payload()},
                headers=self._session_cookie_headers(issued.session_token, issued.csrf_token),
            )
            return

        if not self._authorize_current():
            return

        local = self._local_auth()
        actor = self.auth_actor
        try:
            if self.path == "/api/v1/auth/logout":
                if local is not None and actor is not None:
                    local.logout(actor)
                self._send_json(
                    200,
                    {"authenticated": False},
                    headers=self._clear_session_cookie_headers(),
                )
                return

            if self.path == "/api/v1/auth/reauth":
                if local is None or actor is None:
                    self._send_json(409, {"error": "local identity is unavailable"})
                    return
                issued = local.reauthenticate(actor, str(body.get("password", "")))
                self.auth_actor = issued.actor
                self._send_json(
                    200,
                    {"authenticated": True, "actor": self._actor_payload()},
                    headers=self._session_cookie_headers(issued.session_token, issued.csrf_token),
                )
                return

            if self.path == "/api/v1/admin/users":
                if local is None or actor is None:
                    self._send_json(409, {"error": "local identity is unavailable"})
                    return
                if not self._fresh_administrator_required():
                    return
                roles = body.get("roles", [])
                principal = local.create_user(
                    actor,
                    str(body.get("username", "")),
                    str(body.get("password", "")),
                    tuple(str(role) for role in roles) if isinstance(roles, list) else (),
                )
                self._send_json(201, self._principal_payload(principal))
                return

            if self.path.startswith("/api/v1/admin/users/"):
                if local is None or actor is None:
                    self._send_json(409, {"error": "local identity is unavailable"})
                    return
                if not self._fresh_administrator_required():
                    return
                principal_id = urlsplit(self.path).path.rsplit("/", 1)[-1]
                roles_value = body.get("roles")
                roles = (
                    tuple(str(role) for role in roles_value)
                    if isinstance(roles_value, list)
                    else None
                )
                principal = local.update_user(
                    actor,
                    principal_id,
                    roles=roles,
                    disabled=body.get("disabled")
                    if isinstance(body.get("disabled"), bool)
                    else None,
                    password=(str(body["password"]) if "password" in body else None),
                )
                self._send_json(200, self._principal_payload(principal))
                return

            if self.path == "/api/v1/admin/sessions/revoke-all":
                if local is None or actor is None:
                    self._send_json(409, {"error": "local identity is unavailable"})
                    return
                if not self._fresh_administrator_required():
                    return
                if body.get("confirmation") != "REVOKE ALL SESSIONS":
                    self._send_json(
                        400, {"error": "explicit global revocation confirmation required"}
                    )
                    return
                count = local.revoke_all_sessions(actor)
                self._send_json(
                    200,
                    {"revoked": count},
                    headers=self._clear_session_cookie_headers(),
                )
                return

            if self.path == "/api/v1/admin/tokens":
                if local is None or actor is None:
                    self._send_json(409, {"error": "local identity is unavailable"})
                    return
                if not self._fresh_administrator_required():
                    return
                permissions = body.get("permissions", [])
                issued_token = local.create_automation_token(
                    actor,
                    str(body.get("name", "")),
                    tuple(str(value) for value in permissions)
                    if isinstance(permissions, list)
                    else (),
                    lifetime_seconds=int(body.get("lifetime_seconds", 0)),
                )
                self._send_json(
                    201,
                    {
                        "token": issued_token.token,
                        "token_id": issued_token.token_id,
                        "principal_id": issued_token.principal_id,
                        "username": issued_token.username,
                        "permissions": list(issued_token.permissions),
                        "expires_at": issued_token.expires_at.isoformat(),
                    },
                )
                return
        except (IdentityError, ValueError) as exc:
            if isinstance(exc, IdentityError):
                self._send_identity_error(exc)
            else:
                self._send_json(400, {"error": "invalid request value"})
            return

        if self.path == "/api/v1/setup/configure":
            if not self._setup_access_allowed():
                self._send_json(403, {"error": "setup is restricted to localhost"})
                return
            result = self.setup_handler.configure_dashboard(body)
            status = 200 if result.get("configured") else 400
            if result.get("code") == "configuration_frozen":
                status = 409
            self._send_json(status, result)
            return

        if self.path == "/api/v1/dashboard/llm/models/refresh":
            from samuel.adapters.llm.costs import refresh_pricing

            result = refresh_pricing(
                api_key=os.environ.get("OPENROUTER_API_KEY") or None,
                config=getattr(self.dashboard, "_config", None),
            )
            self._send_json(200 if not result.get("error") else 502, result)
            return

        if self.path == "/api/v1/webhook":
            gitea_event = self.headers.get("X-Gitea-Event", "")
            provider = "gitea" if gitea_event else "github"
            event_type = gitea_event or self.headers.get("X-GitHub-Event", "")
            event_subtype = self.headers.get("X-Gitea-Event-Type", "") or self.headers.get(
                "X-GitHub-Event-Type", ""
            )
            signature = (
                self.headers.get("X-Gitea-Signature", "")
                if provider == "gitea"
                else self.headers.get("X-Hub-Signature-256", "")
            )
            delivery_id = self.headers.get("X-Gitea-Delivery", "") or self.headers.get(
                "X-GitHub-Delivery", ""
            )
            resp = self.webhook_adapter.handle_webhook(
                event_type,
                body,
                signature,
                raw_body=getattr(self, "_raw_request_body", None),
                provider=provider,
                event_subtype=event_subtype,
                delivery_id=delivery_id,
            )
            self._send_json(resp.get("status", 200), resp)
            return

        # #315/#338: Prompt writes remain protected by dashboard API auth.
        if self.path.startswith("/api/v1/dashboard/llm/prompts/"):
            from samuel.adapters.llm.prompts import write_prompt

            blocked = self.dashboard.configuration_mutation_blocked()
            if blocked is not None:
                self._send_json(409, blocked)
                return

            name = self.path[len("/api/v1/dashboard/llm/prompts/") :]
            content = (body or {}).get("content", "")
            scope = (body or {}).get("scope")
            cdir = "config"
            cfg = getattr(self.dashboard, "_config", None)
            if cfg is not None:
                try:
                    cdir = str(cfg.get("agent.config_dir", "config"))
                except Exception as exc:  # noqa: BLE001
                    log.warning("Dashboard config_dir lookup failed: %s", exc)
            result = write_prompt(name, content, cdir, scope=scope)
            if result.get("saved"):
                self.dashboard.mark_configuration_persisted()
            self._send_json(200 if result.get("saved") else 400, result)
            return

        resp = self.rest_api.handle_request(
            "POST", self.path, body=body, headers=dict(self.headers)
        )
        self._send_json(resp.get("status", 200), resp.get("data", resp))

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._authorize_current():
            return

        local = self._local_auth()
        actor = self.auth_actor
        if self.path.startswith("/api/v1/admin/sessions/"):
            if local is None or actor is None or not self._fresh_administrator_required():
                return
            session_id = urlsplit(self.path).path.rsplit("/", 1)[-1]
            self._send_json(200, {"revoked": local.revoke_session(actor, session_id)})
            return
        if self.path.startswith("/api/v1/admin/tokens/"):
            if local is None or actor is None or not self._fresh_administrator_required():
                return
            token_id = urlsplit(self.path).path.rsplit("/", 1)[-1]
            self._send_json(200, {"revoked": local.revoke_automation_token(actor, token_id)})
            return

        # #338 Schicht C: Reset-to-Default — entfernt einen Operator-Override.
        if self.path.startswith("/api/v1/dashboard/llm/prompts/"):
            from urllib.parse import parse_qs, urlparse

            from samuel.adapters.llm.prompts import delete_prompt

            blocked = self.dashboard.configuration_mutation_blocked()
            if blocked is not None:
                self._send_json(409, blocked)
                return

            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            scope_values = qs.get("scope")
            scope_param = scope_values[0] if scope_values else None
            name = parsed.path[len("/api/v1/dashboard/llm/prompts/") :]
            if not name or "/" in name or "\\" in name or ".." in name:
                self._send_json(400, {"error": "invalid prompt name"})
                return
            cdir = "config"
            cfg = getattr(self.dashboard, "_config", None)
            if cfg is not None:
                try:
                    cdir = str(cfg.get("agent.config_dir", "config"))
                except Exception as exc:  # noqa: BLE001
                    log.warning("Dashboard config_dir lookup failed: %s", exc)
            result = delete_prompt(name, cdir, scope=scope_param)
            if result.get("deleted"):
                self.dashboard.mark_configuration_persisted()
            # #364: idempotent — delete_prompt liefert ``deleted=False`` mit
            # ``reason="no override at this scope"`` als No-op-Erfolg, nicht
            # als Fehler. HTTP 400 nur bei echten Fehlern (``error``-Field).
            status = 400 if result.get("error") else 200
            self._send_json(status, result)
            return

        self._send_json(404, {"error": "not found"})


def create_server(
    bus: Bus,
    host: str = "0.0.0.0",
    port: int = 7777,
    scm: Any = None,
    config: Any = None,
    setup_scm_tester: Any = None,
    setup_llm_tester: Any = None,
    configuration_mode: str | None = None,
    authentication: DashboardAuth | Literal[False] | None = None,
) -> ThreadingHTTPServer:
    config_dir = Path(str(config.get("agent.config_dir", "config"))) if config else Path("config")
    if authentication is False:
        _auth = None
        log.warning("Dashboard authentication disabled by an internal test injection")
    elif isinstance(authentication, DashboardAuth):
        _auth = authentication
    else:
        auth_config = AuthRuntimeConfig.load(config_dir)
        api_key = os.environ.get("SAMUEL_API_KEY", "")
        state_store = getattr(bus, "state_store", None)
        identity_store = getattr(state_store, "identity", None)
        local_auth = None
        if identity_store is not None:
            assert state_store is not None
            runtime_state_store = state_store

            def _instance_uuid() -> str:
                return str(runtime_state_store.status().authority_instance)

            def _identity_audit(event: str, actor: str, metadata: dict[str, Any]) -> None:
                from samuel.slices.audit_trail.bridge import log_event

                log_event(
                    event,
                    "identity",
                    event.replace("_", " "),
                    trigger=actor,
                    source="dashboard",
                    meta={"actor": actor, **metadata},
                )

            local_auth = LocalIdentityService(
                identity_store,
                instance_uuid=_instance_uuid,
                absolute_seconds=auth_config.session_absolute_seconds,
                idle_seconds=auth_config.session_idle_seconds,
                fresh_seconds=auth_config.fresh_auth_seconds,
                login_attempts=auth_config.login_attempts,
                login_window_seconds=auth_config.login_window_seconds,
                audit=_identity_audit,
            )
        legacy = APIKeyAuth([api_key]) if api_key else None
        _auth = DashboardAuth(auth_config, legacy=legacy, local=local_auth)
        log.info("Dashboard access mode: %s", auth_config.access_mode)
    webhook_secret = os.environ.get("SLICE_HMAC_KEY", "")
    # #230: Bot-User aus der SCM-Config -> actor_type-Klassifikation (bot vs
    # human) fuer den Activity-Stream. Fehlt die Config, bleibt es leer.
    _bot_user = ""
    try:
        from samuel.core.config import load_scm_config

        _bot_user = load_scm_config().bot_user
    except ValueError:
        # An absent SCM configuration is a supported standalone mode and was
        # already reported by bootstrap.  It is not a runtime problem here.
        log.debug("SCM bot user unavailable because SCM is not configured")
    except Exception as exc:  # noqa: BLE001
        log.warning("SCM bot user could not be loaded: %s", exc)
    _webhooks = WebhookIngressAdapter(bus, secret=webhook_secret, bot_user=_bot_user)
    # Build transfer warning function from privacy config
    transfer_warning_fn = None
    try:
        from pathlib import Path as _Path

        from samuel.slices.privacy.handler import (
            TransferWarning,
            load_configured_provider_names,
        )

        _config_dir = (
            _Path(str(config.get("agent.config_dir", "config"))) if config else _Path("config")
        )
        _privacy_path = _config_dir / "privacy.json"
        if _privacy_path.exists():
            _privacy_data = json.loads(_privacy_path.read_text(encoding="utf-8"))
        else:
            _privacy_data = {}
        _tw = TransferWarning(
            _privacy_data,
            providers=load_configured_provider_names(_config_dir),
        )
        transfer_warning_fn = _tw.check_all_providers
    except Exception as e:
        log.warning("Failed to load transfer warning config: %s", e)
    # #311-followup: balance_resolver wird hier (Wiring-Layer) gebaut, weil
    # samuel/slices/dashboard/* die Adapter-Imports nicht haben darf
    # (test_no_direct_adapter_usage). Server-py ist nicht in slices/.
    _PROVIDERS_WITH_BALANCE_API = frozenset({"deepseek", "openrouter"})

    def _balance_resolver(
        provider: str,
        env_key: str | None,
        url: str | None,
    ) -> tuple[float | None, str]:
        prov = (provider or "").lower()
        if prov in ("ollama", "lmstudio", "manual"):
            return None, "local (no cost)"
        if env_key and not os.environ.get(env_key):
            return None, "no api key"
        if prov not in _PROVIDERS_WITH_BALANCE_API:
            return None, "not provided by API"
        try:
            from unittest.mock import MagicMock

            from samuel.adapters.llm.factory import _build_inner
            from samuel.slices.dashboard.data import _cached_validate

            cfg_stub = MagicMock()
            cfg_stub.get.side_effect = lambda k, d=None: d
            secrets_stub = MagicMock()
            secrets_stub.get.side_effect = lambda k: os.environ.get(k, "")
            adapter = _build_inner(prov, cfg_stub, secrets_stub)
            result = _cached_validate(prov, adapter)
            balance = result.get("balance")
            if balance is None:
                return None, result.get("detail", "unknown")
            return float(balance), "live"
        except Exception as exc:
            log.warning("balance lookup for %s failed: %s", prov, exc)
            return None, "lookup failed"

    # #314: connection_tester — baut temporaeren Adapter aus Form-Werten und ruft validate().
    # Wiring-Layer (server.py) darf adapter direkt importieren; slice darf das nicht.
    def _connection_tester(provider: str, cfg: dict) -> dict:
        prov = (provider or "").lower()
        try:
            from unittest.mock import MagicMock

            from samuel.adapters.llm.factory import _build_inner

            cfg_stub = MagicMock()
            cfg_stub.get.side_effect = lambda k, d=None: d
            secrets_stub = MagicMock()
            secrets_stub.get.side_effect = lambda k: os.environ.get(k, "")
            adapter = _build_inner(
                prov,
                cfg_stub,
                secrets_stub,
                model_override=cfg.get("model"),
                base_url_override=cfg.get("base_url"),
                timeout_override=int(cfg["timeout"]) if cfg.get("timeout") else None,
            )
            validator = getattr(adapter, "validate", None)
            if not callable(validator):
                return {"valid": False, "detail": "validate() not implemented", "balance": None}
            raw_result = validator()
            result = raw_result if isinstance(raw_result, dict) else {}
            return {
                "valid": bool(result.get("valid")),
                "detail": str(result.get("detail", "")),
                "balance": result.get("balance"),
            }
        except Exception as exc:
            log.warning("test_connection for %s failed: %s", prov, exc)
            return {"valid": False, "detail": f"test failed: {exc}", "balance": None}

    def _default_setup_scm_tester(
        provider: str,
        url: str,
        token: str,
        repo: str,
    ) -> dict[str, Any]:
        try:
            from samuel.adapters.auth.static_token import StaticTokenAuth
            from samuel.adapters.gitea.adapter import GiteaAdapter
            from samuel.adapters.github.adapter import GitHubAdapter

            auth = StaticTokenAuth(token)
            adapter = (
                GiteaAdapter(url, repo, auth)
                if provider == "gitea"
                else GitHubAdapter(repo, auth, base_url=url)
            )
            adapter.list_labels()
            return {"valid": True, "detail": f"repository {repo} reachable"}
        except Exception as exc:  # noqa: BLE001
            log.warning("Dashboard setup SCM probe failed: %s", exc)
            return {"valid": False, "detail": f"connection failed: {exc}"}

    def _default_setup_llm_tester(
        provider: str,
        cfg: dict[str, Any],
        secret: str,
    ) -> dict[str, Any]:
        try:
            from unittest.mock import MagicMock

            from samuel.adapters.llm.factory import _build_inner

            cfg_stub = MagicMock()
            cfg_stub.get.side_effect = lambda _key, default=None: default
            secrets_stub = MagicMock()
            secrets_stub.get.side_effect = lambda _key: secret
            adapter = _build_inner(
                provider,
                cfg_stub,
                secrets_stub,
                model_override=cfg.get("model") or None,
                base_url_override=cfg.get("base_url") or None,
            )
            validator = getattr(adapter, "validate", None)
            if not callable(validator):
                return {"valid": False, "detail": "validate() not implemented"}
            raw_result = validator()
            result = raw_result if isinstance(raw_result, dict) else {}
            return {
                "valid": bool(result.get("valid")),
                "detail": str(result.get("detail", "")),
            }
        except Exception as exc:  # noqa: BLE001
            log.warning("Dashboard setup LLM probe failed for %s: %s", provider, exc)
            return {"valid": False, "detail": f"connection failed: {exc}"}

    # #348: prompt_source_resolver — Wiring-Schicht darf den Adapter
    # direkt importieren; die Slice (data.py) darf das nicht. Damit kann
    # der Editor pro Task ausweisen, welche Cascade-Stufe gerade greift
    # (package / operator-generic / operator-provider:X / operator-model:Y).
    from samuel.adapters.llm.prompts import resolve_prompt_source

    def _prompt_source_resolver(
        name: str,
        cdir: str,
        provider: str | None,
        model: str | None,
        by_provider: dict | None = None,
    ) -> dict:
        return resolve_prompt_source(
            name,
            cdir,
            provider=provider,
            model=model,
            by_provider=by_provider,
        )

    def _model_quality_resolver(
        model: str, task: str, threshold: float, margin_ratio: float
    ) -> dict:
        from samuel.adapters.llm.costs import (
            get_model_reasoning_info,
            get_model_suitability,
        )

        return {
            "reasoning": get_model_reasoning_info(model),
            "suitability": get_model_suitability(
                model,
                task,
                threshold=threshold,
                overqualification_margin_ratio=margin_ratio,
            ),
        }

    def _model_cache_status_resolver() -> dict:
        from samuel.adapters.llm.costs import get_pricing_info

        return get_pricing_info()

    from samuel.core.configuration_mode import ConfigurationAuthority

    _configuration_authority = ConfigurationAuthority.resolve(config_dir, configuration_mode)

    # Bootstrap owns the durable registry. Isolated server tests may omit it.
    _quality_registry = getattr(bus, "quality_registry", None)
    _dash = DashboardHandler(
        bus,
        scm=scm,
        config=config,
        transfer_warning_fn=transfer_warning_fn,
        balance_resolver=_balance_resolver,
        connection_tester=_connection_tester,
        prompt_source_resolver=_prompt_source_resolver,
        model_quality_resolver=_model_quality_resolver,
        model_cache_status_resolver=_model_cache_status_resolver,
        llm_activity_resolver=getattr(bus, "llm_activity_resolver", None),
        quality_registry=_quality_registry,
        observation_store=getattr(bus, "observation_store", None),
        run_projection_store=getattr(bus, "run_projection_store", None),
        product_version=__build_info__.product_version,
        build_revision=__build_info__.revision,
        build_dirty=__build_info__.dirty,
        build_revision_source=__build_info__.revision_source,
        configuration_authority=_configuration_authority,
    )
    _setup = SetupHandler(
        bus,
        config=config,
        project_root=config_dir.parent,
        scm=scm,
        scm_tester=setup_scm_tester or _default_setup_scm_tester,
        llm_tester=setup_llm_tester or _default_setup_llm_tester,
        configuration_authority=_configuration_authority,
    )
    # The HTTP handler already authenticates and authorizes each concrete route.
    # RestAPI keeps its own optional auth hook for direct adapter consumers.
    _rest = RestAPI(bus, setup_handler=_setup, dashboard_handler=_dash)

    class Handler(SAMUELRequestHandler):
        rest_api = _rest
        webhook_adapter = _webhooks
        dashboard = _dash
        setup_handler = _setup
        auth_middleware = _auth

    server = ThreadingHTTPServer((host, port), Handler)
    bound_host, bound_port = server.server_address[:2]
    log.info("HTTP-Server auf %s:%d", bound_host, bound_port)
    return server
