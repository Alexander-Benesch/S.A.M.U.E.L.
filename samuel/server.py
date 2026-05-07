from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from samuel.adapters.api.auth import APIKeyAuth
from samuel.adapters.api.rest import RestAPI
from samuel.adapters.api.webhooks import WebhookIngressAdapter
from samuel.core.bus import Bus
from samuel.slices.dashboard.handler import DashboardHandler
from samuel.slices.setup.handler import SetupHandler

log = logging.getLogger(__name__)

DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>S.A.M.U.E.L. Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#e2e8f0;padding:1.5rem;max-width:1200px;margin:0 auto}
header{display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;flex-wrap:wrap;gap:.5rem}
header h1{font-size:1.5rem;color:#38bdf8}
header h1 span{font-size:.75rem;color:#64748b;font-weight:400;margin-left:.5rem}
.meta{font-size:.75rem;color:#64748b;text-align:right}
.countdown{font-size:.7rem;color:#64748b}
.tabs{display:flex;gap:2px;margin-bottom:1rem;border-bottom:2px solid #334155;overflow-x:auto}
.tab{background:transparent;color:#94a3b8;border:none;padding:.75rem 1.25rem;cursor:pointer;font-size:.875rem;border-bottom:2px solid transparent;margin-bottom:-2px;white-space:nowrap}
.tab.active{color:#38bdf8;border-bottom-color:#38bdf8}
.tab:hover{color:#e2e8f0}
.tab-content{display:none}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:1rem;margin-bottom:1.5rem}
.card{background:#1e293b;border-radius:8px;padding:1rem;border:1px solid #334155;transition:border-color .2s}
.card:hover{border-color:#475569}
.card h3{font-size:.7rem;color:#94a3b8;margin-bottom:.4rem;text-transform:uppercase;letter-spacing:.05em}
.card .val{font-size:1.4rem;font-weight:700}
.ok{color:#4ade80}.warn{color:#fbbf24}.err{color:#f87171}
.section{background:#1e293b;border-radius:8px;padding:1rem;border:1px solid #334155;margin-bottom:1rem}
.section h2{font-size:.875rem;color:#94a3b8;margin-bottom:.75rem;text-transform:uppercase;letter-spacing:.05em}
.health-row{display:flex;justify-content:space-between;padding:.4rem 0;border-bottom:1px solid #334155;font-size:.85rem}
.health-row:last-child{border-bottom:none}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:.4rem;vertical-align:middle}
.dot.g{background:#4ade80}.dot.r{background:#f87171}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:.5rem .75rem;border-bottom:1px solid #334155}
th{color:#94a3b8;font-size:.7rem;text-transform:uppercase}
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
.filter-bar select,.filter-bar input{background:#1e293b;color:#e2e8f0;border:1px solid #475569;padding:.5rem;border-radius:4px;font-size:.8rem}
.filter-bar input{flex:1;min-width:150px}
.warn-item{background:#422006;border:1px solid #92400e;border-radius:6px;padding:.75rem;margin-bottom:.5rem;font-size:.85rem}
.warn-item:last-child{margin-bottom:0}
.toggle{position:relative;display:inline-block;width:40px;height:22px;vertical-align:middle}
.toggle input{opacity:0;width:0;height:0}
.toggle .slider{position:absolute;cursor:default;inset:0;background:#475569;border-radius:11px;transition:.2s}
.toggle input:checked+.slider{background:#0ea5e9}
.toggle .slider::before{content:'';position:absolute;height:16px;width:16px;left:3px;bottom:3px;background:#e2e8f0;border-radius:50%;transition:.2s}
.toggle input:checked+.slider::before{transform:translateX(18px)}
.flag-row{display:flex;justify-content:space-between;align-items:center;padding:.6rem 0;border-bottom:1px solid #334155;font-size:.85rem}
.flag-row:last-child{border-bottom:none}
.empty{color:#64748b;font-style:italic;padding:1rem;text-align:center}
@media(max-width:600px){header{flex-direction:column;align-items:flex-start}.meta{text-align:left}.grid{grid-template-columns:1fr 1fr}}
</style>
</head>
<body>
<header>
 <h1>S.A.M.U.E.L.<span>v2.0.0-alpha</span></h1>
 <div class="meta">
  <div>Letztes Update: <span id="last-refresh">-</span>
   <button id="auto-refresh-btn" onclick="toggleAutoRefresh()" style="background:#1e293b;color:#e2e8f0;border:1px solid #475569;padding:.2rem .5rem;border-radius:4px;font-size:.7rem;cursor:pointer;margin-left:.5rem">auto-refresh: on</button>
  </div>
  <div class="countdown">Naechstes Update in <span id="countdown">10</span>s</div>
 </div>
</header>
<div id="toast" style="position:fixed;top:1rem;right:1rem;padding:.75rem 1rem;border-radius:6px;font-size:.85rem;display:none;z-index:1000;max-width:400px"></div>
<nav class="tabs">
 <button class="tab active" onclick="showTab('status')">Status</button>
 <button class="tab" onclick="showTab('llm')">LLM &amp; Kosten</button>
 <button class="tab" onclick="showTab('workflow')">Workflow</button>
 <button class="tab" onclick="showTab('logs')">Logs</button>
 <button class="tab" onclick="showTab('security')">Security</button>
 <button class="tab" onclick="showTab('compliance')">Compliance</button>
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
 <div class="section"><h2>Activity (Commands / Events)</h2>
  <table><thead><tr><th>Command/Event</th><th>Count</th><th>Errors</th><th>Avg ms</th></tr></thead>
  <tbody id="s-activity"></tbody></table>
 </div>
 <div class="section"><h2>Score-History (letzte 15 Evals)</h2>
  <table><thead><tr><th>Zeit</th><th>Issue</th><th>Score</th><th>Baseline</th><th>Pass</th><th>Reason</th></tr></thead>
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
  <div class="card"><h3>Provider</h3><div class="val" id="l-provider">-</div></div>
 </div>
 <div class="section"><h2>API-Key-Status</h2>
  <table><thead><tr><th>Provider</th><th>Model</th><th>Status</th><th>Key/URL</th><th>Hinweis</th></tr></thead>
  <tbody id="l-keys"></tbody></table>
 </div>
 <div class="section"><h2>Routing pro Task</h2>
  <div id="l-schedule" style="font-size:.75rem;color:#94a3b8;margin-bottom:.5rem">-</div>
  <table><thead><tr><th>Task</th><th>Provider</th><th>Model</th><th>max_tokens</th><th>temp</th><th>timeout</th></tr></thead>
  <tbody id="l-routing"></tbody></table>
 </div>
 <div class="section"><h2>Token Usage per Task</h2>
  <table><thead><tr><th>Task</th><th>Calls</th><th>Tokens</th><th>Cost</th></tr></thead>
  <tbody id="l-tasks"></tbody></table>
 </div>
 <div class="section"><h2>Token-History (letzte 50 Calls) <span style="font-size:.7rem;color:#64748b;font-weight:400">— hover ueber Details fuer Listen</span></h2>
  <table><thead><tr><th>Zeit</th><th>Provider</th><th>Model</th><th>Task</th><th>in</th><th>out</th><th>cached</th><th>total</th><th>Cost</th><th>Latency ms</th><th>Issue</th><th>Details</th></tr></thead>
  <tbody id="l-history"></tbody></table>
 </div>
 <div class="section"><h2>Quality-Scores (Provider/Model/Task) <span style="font-size:.7rem;color:#64748b;font-weight:400">— Korrelation ueber correlation_id, blockiert wo Eval fehlt</span></h2>
  <table><thead><tr><th>Provider</th><th>Model</th><th>Task</th><th>Calls</th><th>Graded</th><th>Passed</th><th>Failed</th><th>Success %</th><th>Avg Score</th><th>Last</th></tr></thead>
  <tbody id="l-quality"></tbody></table>
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
   <div class="card"><h3>Score</h3><div class="val" id="wd-score">-</div></div>
   <div class="card"><h3>LLM Calls</h3><div class="val" id="wd-llm-calls">-</div></div>
   <div class="card"><h3>LLM Tokens</h3><div class="val" id="wd-llm-tokens">-</div></div>
   <div class="card"><h3>LLM Cost</h3><div class="val" id="wd-llm-cost">-</div></div>
  </div>
  <h3 style="font-size:.85rem;color:#94a3b8;margin:1rem 0 .5rem;text-transform:uppercase">Pipeline Stages</h3>
  <div id="wd-stages" style="display:flex;flex-wrap:wrap;gap:.5rem;margin-bottom:1rem"></div>
  <h3 style="font-size:.85rem;color:#94a3b8;margin:1rem 0 .5rem;text-transform:uppercase">LLM Calls</h3>
  <table><thead><tr><th>Zeit</th><th>Task</th><th>Provider/Model</th><th>Tokens</th><th>Cost</th><th>Latenz</th><th>Guards</th><th>Tools</th><th>Context</th><th>est.&nbsp;Tokens</th></tr></thead>
  <tbody id="wd-llm-detail"></tbody></table>
  <h3 style="font-size:.85rem;color:#94a3b8;margin:1rem 0 .5rem;text-transform:uppercase">Test Runs</h3>
  <table><thead><tr><th>Zeit</th><th>Test</th><th>Runner</th><th>Status</th><th>Dauer</th><th>Exit</th></tr></thead>
  <tbody id="wd-test-runs"></tbody></table>
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
 <div class="section"><h2>Tamper-Alerts</h2>
  <table><thead><tr><th>Zeit</th><th>Event</th><th>OWASP</th><th>Detail</th><th>Issue</th></tr></thead>
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
  <p style="font-size:.8rem;color:#94a3b8;margin-bottom:.5rem">Artikel-Nummern aus VO (EU) 2024/1689 wie sie im Audit-Trail (Spalte AI Act) erscheinen.</p>
  <table><thead><tr><th>Artikel</th><th>Beschreibung</th></tr></thead>
  <tbody id="comp-aiact"></tbody></table>
 </div>
</div>

<!-- TAB: SETTINGS -->
<div class="tab-content" id="tab-settings">
 <div class="section"><h2>Feature Flags</h2><div id="set-flags"><div class="empty">Laden...</div></div></div>
 <div class="section"><h2>Setup</h2>
  <button id="btn-sync-labels" onclick="syncLabels()" style="background:#0ea5e9;color:#0f172a;border:none;padding:.5rem 1rem;border-radius:4px;font-size:.85rem;cursor:pointer;font-weight:600">Labels auf SCM synchronisieren</button>
  <div id="labels-result" style="margin-top:.75rem;font-size:.8rem;color:#94a3b8"></div>
 </div>
 <div class="section"><h2>Premium</h2><div id="set-premium"><div class="empty">Laden...</div></div></div>
 <div class="section"><h2>LLM Configuration</h2><div id="set-llm-config"><div class="empty">Laden...</div></div></div>
 <div class="section"><h2>API Keys</h2><div id="set-api-keys"><div class="empty">Laden...</div></div></div>
 <div class="section" id="set-warnings-section" style="display:none"><h2>Transfer-Warnungen (DSGVO)</h2><div id="set-warnings"></div></div>
</div>

<!-- TAB: SELF-CHECK -->
<div class="tab-content" id="tab-selfcheck">
 <div class="grid">
  <div class="card"><h3>Modus</h3><div class="val" id="sc-mode">-</div></div>
  <div class="card"><h3>Status</h3><div class="val" id="sc-healthy">-</div></div>
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
const ts=()=>new Date().toLocaleTimeString('de-DE');
const esc=s=>{const d=document.createElement('div');d.textContent=s;return d.innerHTML};
const fmt=n=>typeof n==='number'?n.toLocaleString('de-DE'):(n||'-');

// #359: Compliance-Legende lazy-cachen, damit Click-Expand auf OWASP-/AI-Act-
// Codes im Audit-Trail und Schranken-Protokoll ohne Roundtrip pro Klick laeuft.
let complianceCache=null;
async function ensureLegend(){
 if(complianceCache)return complianceCache;
 try{
  const r=await apiFetch('/api/v1/dashboard/compliance/legend');
  const j=await r.json();const d=j.data||j;
  complianceCache={owasp:d.owasp||[],ai_act:d.ai_act||[]};
 }catch(e){complianceCache={owasp:[],ai_act:[]};}
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

function apiHeaders(){
 const k=sessionStorage.getItem('apiKey')||'';
 return k?{'X-API-Key':k}:{};
}
function apiFetch(url,opts){
 opts=opts||{};
 const h=Object.assign({},opts.headers||{},apiHeaders());
 return fetch(url,Object.assign({},opts,{headers:h}));
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
  else if(tab==='workflow')await loadWorkflow();
  else if(tab==='logs')await loadLogs();
  else if(tab==='security')await loadSecurity();
  else if(tab==='compliance')await loadCompliance();
  else if(tab==='settings')await loadSettings();
  else if(tab==='selfcheck')await loadSelfCheck();
  document.getElementById('last-refresh').textContent=ts();
 }catch(e){console.error('Tab load failed:',tab,e)}
}

async function loadStatus(){
 const[sr,hr]=await Promise.all([
  apiFetch('/api/v1/dashboard/status').then(r=>r.json()),
  apiFetch('/api/v1/dashboard/health').then(r=>r.json())
 ]);
 const hd=hr.data||hr;
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
 if(!(sr.tiles||[]).length)tilesDiv.innerHTML='<div class="empty" style="grid-column:1/-1">Keine Tiles</div>';
 const sh=document.getElementById('s-score-history');sh.innerHTML='';
 const hist=sr.score_history||[];
 if(hist.length){hist.forEach(h=>{
  const cls=h.passed?'ok':'err';
  sh.innerHTML+='<tr><td style="font-size:.75rem">'+esc(h.timestamp||'-')+'</td><td>'+(h.issue?'#'+esc(String(h.issue)):'-')+'</td><td>'+(h.score!=null?String(h.score):'-')+'</td><td>'+(h.baseline!=null?String(h.baseline):'-')+'</td><td class="'+cls+'">'+(h.passed?'PASS':'FAIL')+'</td><td style="font-size:.75rem">'+esc(h.reason||'-')+'</td></tr>';
 });}else{sh.innerHTML='<tr><td colspan="6" class="empty">Keine Eval-Events</td></tr>';}
 const an=document.getElementById('s-anomalies');an.innerHTML='';
 const anoms=sr.anomalies||[];
 if(anoms.length){anoms.forEach(a=>{
  const cls=a.level==='error'?'err':'warn';
  an.innerHTML+='<tr><td style="font-size:.75rem">'+esc(a.timestamp||'-')+'</td><td class="'+cls+'">'+esc(a.level||'-')+'</td><td>'+esc(a.event||'-')+'</td><td>'+(a.issue?'#'+esc(String(a.issue)):'-')+'</td><td style="font-size:.8rem">'+esc(a.message||'-')+'</td></tr>';
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
  schedDiv.textContent='Day/Night-Routing AKTIV — Tag: '+(sched.day_provider||'(default)')+' | Nacht ('+sched.night_hours+'): '+(sched.night_provider||'(default)');
  schedDiv.style.color='#fbbf24';
 }else{schedDiv.textContent='Day/Night-Routing inaktiv (premium.llm_routing.enabled=false)';schedDiv.style.color='#64748b';}
 const rb=document.getElementById('l-routing');rb.innerHTML='';
 const routing=data.routing||[];
 if(Array.isArray(routing)&&routing.length){
  routing.forEach(r=>{rb.innerHTML+='<tr><td>'+esc(r.task||'-')+'</td><td>'+esc(r.provider||'-')+'</td><td>'+esc(r.model||'-')+'</td><td>'+(r.max_tokens!=null?fmt(r.max_tokens):'-')+'</td><td>'+(r.temperature!=null?Number(r.temperature).toFixed(2):'-')+'</td><td>'+(r.timeout!=null?fmt(r.timeout):'-')+'</td></tr>';});
 }else{rb.innerHTML='<tr><td colspan="6" class="empty">Keine Routing-Daten</td></tr>';}
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
  hb.innerHTML+='<tr><td>'+esc(h.timestamp||'-')+'</td><td>'+esc(h.provider||'-')+'</td><td>'+esc(h.model||'-')+'</td><td>'+esc(h.task||'-')+'</td><td>'+(h.input_tokens!=null?fmt(h.input_tokens):'-')+'</td><td>'+(h.output_tokens!=null?fmt(h.output_tokens):'-')+'</td><td>'+(h.cached_tokens!=null?fmt(h.cached_tokens):'-')+'</td><td>'+(h.tokens!=null?fmt(h.tokens):'-')+'</td><td>'+(h.cost!=null?Number(h.cost).toFixed(4):'-')+'</td><td>'+(h.latency_ms!=null?fmt(h.latency_ms):'-')+'</td><td>'+(h.issue?'#'+esc(String(h.issue)):'-')+'</td>'+detailCell+'</tr>';
 });}else{hb.innerHTML='<tr><td colspan="12" class="empty">Keine LLM-Calls im Audit-Log</td></tr>';}
 const qb=document.getElementById('l-quality');qb.innerHTML='';
 const qual=data.quality||[];
 if(qual.length){qual.forEach(q=>{
  const sr=q.success_rate_pct;const cls=sr==null?'':sr>=80?'ok':sr>=50?'warn':'err';
  qb.innerHTML+='<tr><td>'+esc(q.provider||'-')+'</td><td>'+esc(q.model||'-')+'</td><td>'+esc(q.task||'-')+'</td><td>'+fmt(q.calls||0)+'</td><td>'+fmt(q.graded||0)+'</td><td>'+fmt(q.passed||0)+'</td><td>'+fmt(q.failed||0)+'</td><td class="'+cls+'">'+(sr!=null?sr+'%':'-')+'</td><td>'+(q.avg_score!=null?Number(q.avg_score).toFixed(2):'-')+'</td><td style="font-size:.75rem">'+esc(q.last_ts||'-')+'</td></tr>';
 });}else{qb.innerHTML='<tr><td colspan="10" class="empty">Keine Quality-Korrelation moeglich</td></tr>';}
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
   ib.innerHTML+='<tr data-issue="'+esc(String(num))+'" style="cursor:pointer"><td>#'+esc(String(num||'-'))+'</td><td><span class="'+cls+'">'+esc(i.status||'-')+'</span></td><td>'+esc(i.last_event||'-')+'</td><td>'+esc(i.timestamp||'-')+'</td><td>'+runs+'</td><td style="color:'+trCol+'">'+esc(trLabel)+'</td></tr>';
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
 document.getElementById('wd-score').textContent=(sv!=null?sv:'-')+(sc.baseline!=null?(' / '+sc.baseline):'')+(passed===true?' OK':passed===false?' FAIL':'');
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
  ldb.innerHTML+='<tr><td style="font-size:.75rem">'+esc(c.timestamp||'-')+'</td><td>'+esc(c.task||'-')+'</td><td style="font-size:.8rem">'+pm+'</td><td>'+fmt(c.tokens||0)+'</td><td>'+(c.cost!=null?Number(c.cost).toFixed(4):'-')+'</td><td>'+(c.latency_ms!=null?fmt(c.latency_ms)+'ms':'-')+'</td><td style="font-size:.75rem;color:#94a3b8">'+esc(guards||'-')+'</td><td style="font-size:.75rem;color:#94a3b8">'+esc(tools||'-')+'</td><td style="font-size:.75rem;color:#94a3b8">'+esc(ctx||'-')+'</td><td>'+est+'</td></tr>';
 });}else{ldb.innerHTML='<tr><td colspan="10" class="empty">Keine LLM-Calls</td></tr>';}
 const sb=document.getElementById('wd-stages');sb.innerHTML='';
 const stages=d.stages||{};
 ['plan','implement','llm','gates','quality','eval','pr','review'].forEach(s=>{
  const st=stages[s]||{status:'pending',count:0,fail_count:0};
  const col=st.status==='done'?'#22c55e':st.status==='failed'?'#ef4444':'#475569';
  sb.innerHTML+='<div style="background:'+col+';color:#fff;padding:.4rem .8rem;border-radius:4px;font-size:.8rem">'+esc(s)+': '+esc(st.status)+(st.count?' ('+st.count+(st.fail_count?'/'+st.fail_count+'!':'')+')':'')+'</div>';
 });
 const tb=document.getElementById('wd-test-runs');tb.innerHTML='';
 const truns=Array.isArray(d.test_runs)?d.test_runs:[];
 if(!truns.length){tb.innerHTML='<tr><td colspan="6" class="empty">Keine Test-Runs</td></tr>';}
 else{truns.slice().reverse().forEach(t=>{
  const status=t.passed?'<span class="ok">PASS</span>':'<span class="err">FAIL</span>';
  const dur=t.duration_ms!=null?fmt(t.duration_ms)+'ms':'-';
  const exit=t.exit_code!=null?String(t.exit_code):'-';
  tb.innerHTML+='<tr><td>'+esc(t.timestamp||'-')+'</td><td>'+esc(t.test_name||'-')+'</td><td>'+esc(t.runner||'-')+'</td><td>'+status+'</td><td>'+dur+'</td><td>'+esc(exit)+'</td></tr>';
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
   rb.innerHTML+='<tr><td>'+(idx+1)+'</td><td style="font-size:.75rem">'+esc(rn.start_ts||'-')+'</td><td style="font-size:.75rem">'+esc(rn.end_ts||'-')+'</td><td>'+scoreCell+'</td><td>'+stages+'</td><td style="color:'+sCol+'">'+esc(fs)+'</td><td>'+pr+'</td></tr>';
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
  eb.innerHTML+='<tr><td>'+esc(e.timestamp||'-')+'</td><td class="'+cls+'">'+esc(e.level||'-')+'</td><td>'+esc(e.category||'-')+'</td><td>'+esc(e.event||'-')+'</td><td>'+esc(e.message||'-')+'</td>'+owCell+aiCell+'</tr>'+
   '<tr class="trail-info-row" data-trail-info-for="'+idx+'" style="display:none"><td colspan="7" data-trail-info-content style="font-size:.75rem;background:#1e293b;padding:.5rem .75rem;color:#cbd5e1"></td></tr>';
 });
}

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
  const resolved=l.resolved_at?' <span style="background:#065f46;color:#d1fae5;padding:1px 6px;border-radius:3px;font-size:.7rem" title="Behoben am '+esc(l.resolved_at)+'">RESOLVED</span>':'';
  tb.innerHTML+='<tr class="log-row" data-meta-idx="'+idx+'"'+(hasMeta?' style="cursor:pointer"':'')+'>'+
   '<td>'+toggle+'</td>'+
   '<td>'+esc(l.timestamp||'-')+'</td>'+
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
  if(kind==='ai_act'){const desc=aiActDesc(txt);if(desc)html+='<div style="color:#60a5fa;margin-top:.2rem"><strong>'+esc(txt)+':</strong> '+esc(desc)+'</div>';}
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
  banner.style.display='block';
  banner.innerHTML='<strong>SECURITY ALERT &mdash; '+tamper.length+' Manipulationsversuch(e) erkannt</strong>';
 }else{banner.style.display='none';banner.innerHTML='';}
 const bp=data.branch_protection||{};
 const bpDiv=document.getElementById('sec-branch-protection');
 const bpBranch=esc(bp.branch||'main');
 if(!bp.available){
  bpDiv.innerHTML='<div class="empty">SCM unterstuetzt Branch-Protection nicht oder ist nicht verbunden ('+bpBranch+')</div>';
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
   bb.innerHTML+='<tr style="'+bg+'"><td>'+esc(b.timestamp||'-')+'</td><td>'+(b.issue?'#'+esc(String(b.issue)):'-')+'</td><td>'+esc(b.step||'-')+'</td><td>'+esc(b.event||'-')+'</td><td>'+esc(b.action||'-')+'</td>'+owCell+'<td>'+esc(b.detail||'-')+'</td></tr>'+
    '<tr class="barrier-info-row" data-barrier-info-for="'+idx+'" style="display:none"><td colspan="7" data-barrier-info-content style="font-size:.75rem;background:#1e293b;padding:.5rem .75rem;color:#cbd5e1"></td></tr>';
  });
 }
 else{bb.innerHTML='<tr><td colspan="7" class="empty">Keine Schranken-Events</td></tr>';}
 const otel=data.otel_calls||[];
 const ot=document.getElementById('sec-otel');ot.innerHTML='';
 if(otel.length){otel.forEach(o=>{
  ot.innerHTML+='<tr><td>'+esc(o.timestamp||'-')+'</td><td>'+esc(o['gen_ai.system']||'-')+'</td><td>'+esc(o['gen_ai.request.model']||'-')+'</td><td>'+(o['gen_ai.usage.input_tokens']!=null?fmt(o['gen_ai.usage.input_tokens']):'-')+'</td><td>'+(o['gen_ai.usage.output_tokens']!=null?fmt(o['gen_ai.usage.output_tokens']):'-')+'</td><td>'+(o['gen_ai.usage.total_tokens']!=null?fmt(o['gen_ai.usage.total_tokens']):'-')+'</td><td>'+(o['gen_ai.client.operation.duration']!=null?Number(o['gen_ai.client.operation.duration']).toFixed(0):'-')+'</td><td>'+esc(o['gen_ai.response.finish_reasons']||'-')+'</td><td>'+esc(o.task||'-')+'</td></tr>';
 });}
 else{ot.innerHTML='<tr><td colspan="9" class="empty">Keine OTel-Calls</td></tr>';}
 const tb2=document.getElementById('sec-tamper');tb2.innerHTML='';
 if(tamper.length){tamper.forEach(t=>{tb2.innerHTML+='<tr><td>'+esc(t.ts||'-')+'</td><td>'+esc(t.event||'-')+'</td><td>'+esc(t.owasp||'-')+'</td><td>'+esc(t.detail||'-')+'</td><td>'+(t.issue?'#'+esc(String(t.issue)):'-')+'</td></tr>';});}
 else{tb2.innerHTML='<tr><td colspan="5" class="empty">Keine Tamper-Events</td></tr>';}
}
document.getElementById('sec-owasp').addEventListener('click',e=>{
 const tr=e.target.closest('tr[data-owasp-idx]');if(!tr)return;
 const idx=parseInt(tr.dataset.owaspIdx,10);const o=secOwasp[idx];
 if(!o||!(o.recent||[]).length)return;
 const box=document.getElementById('sec-owasp-recent');
 let html='<div class="section" style="margin-top:.5rem"><h3 style="font-size:.85rem;color:#94a3b8;text-transform:uppercase;margin-bottom:.5rem">'+esc(o.id)+' &mdash; '+esc(o.category)+' (Recent '+o.recent.length+')</h3><table><thead><tr><th>Zeit</th><th>Event</th><th>Message</th><th>Issue</th></tr></thead><tbody>';
 o.recent.forEach(r=>{html+='<tr><td>'+esc(r.timestamp||'-')+'</td><td>'+esc(r.event||'-')+'</td><td>'+esc(r.message||'-')+'</td><td>'+(r.issue?'#'+esc(String(r.issue)):'-')+'</td></tr>';});
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
 const at=document.getElementById('comp-aiact');at.innerHTML='';
 (d.ai_act||[]).forEach(r=>{
  at.innerHTML+='<tr><td><strong>'+esc(r.article||'-')+'</strong></td><td>'+esc(r.description||'-')+'</td></tr>';
 });
}

async function loadSettings(){
 const[sd,st]=await Promise.all([
  apiFetch('/api/v1/dashboard/settings').then(r=>r.json()),
  apiFetch('/api/v1/dashboard/status').then(r=>r.json())
 ]);
 const sdata=sd.data||sd;
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
 }else{fDiv.innerHTML='<div class="empty">Keine Feature Flags</div>';}
 const premium=sdata.premium_status||{active:false,reason:'no data'};
 const pDiv=document.getElementById('set-premium');
 if(premium.active){
  const feats=(premium.features||[]).join(', ');
  pDiv.innerHTML='<div class="flag-row"><span style="color:#10b981;font-weight:600">PREMIUM aktiv</span><span style="color:#94a3b8">'+esc(premium.email||'')+' &middot; '+esc(feats)+'</span></div>';
 }else{
  pDiv.innerHTML='<div class="flag-row"><span style="color:#f59e0b;font-weight:600">FREE MODE</span><span style="color:#94a3b8">'+esc(premium.reason||'no license')+'</span></div>';
 }
 // #309: LLM-Config Edit (Premium llm_routing_dashboard_write)
 const canEditLLM=premium.active&&(premium.features||[]).indexOf('llm_routing_dashboard_write')>=0;
 window.__canEditLLM=canEditLLM;
 // #316: Schedule-Block (Premium llm_routing_advanced) — separate Feature
 window.__canScheduleLLM=premium.active&&(premium.features||[]).indexOf('llm_routing_advanced')>=0;
 const llmCfg=sdata.llm_config||[];
 const cDiv=document.getElementById('set-llm-config');cDiv.innerHTML='';
 if(Array.isArray(llmCfg)&&llmCfg.length){llmCfg.forEach(row=>{
  const task=row.task||'?';
  const prov=row.provider||'-';
  const model=row.model||'-';
  // #312: Edit-Icon mit Spacing + Bleistift-Symbol statt "edit" — Layout-Fix.
  const editIcon=canEditLLM
   ?' <button onclick="openLLMTaskEditor(\\''+esc(task)+'\\')" title="Konfiguration bearbeiten" style="background:transparent;border:1px solid #334155;cursor:pointer;color:#0ea5e9;font-size:.8rem;margin-left:.75rem;padding:.15rem .5rem;border-radius:3px">&#9998; edit</button>'
   :' <span title="Premium-Feature llm_routing_dashboard_write erforderlich" style="color:#475569;font-size:.7rem;margin-left:.75rem;padding:.15rem .4rem;border:1px solid #334155;border-radius:3px">premium</span>';
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

// #309/#312: Per-Task LLM-Config Inline-Editor (Premium llm_routing_dashboard_write)
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
  '<label>Model</label><div style="display:flex;gap:.3rem"><select id="ed-model-'+task+'" style="flex:1"><option value="'+esc(cfg.model||'')+'">'+esc(cfg.model||'(loading...)')+'</option></select>'+
  '<button onclick="loadModelsForProvider(\\''+task+'\\')" title="Refresh OpenRouter-Cache + reload" style="background:#1e293b;border:1px solid #334155;color:#e2e8f0;cursor:pointer;padding:.15rem .5rem;border-radius:3px;font-size:.75rem">&#x21bb;</button></div>'+
  '<label></label><span id="ed-modelnote-'+task+'" style="color:#64748b;font-size:.7rem"></span>'+
  '<label>base_url</label><input id="ed-baseurl-'+task+'" value="'+esc(cfg.base_url||'')+'" placeholder="auto-fill je Provider">'+
  '<label></label><span id="ed-urlnote-'+task+'" style="color:#64748b;font-size:.7rem"></span>'+
  '<label>timeout (s)</label><input id="ed-timeout-'+task+'" value="'+esc(cfg.timeout||'')+'" type="number">'+
  // #315: system_prompt-Dropdown dynamisch + View/Edit-Buttons.
  // #348: Source-Badge zeigt welche Cascade-Stufe greift (package/operator-...).
  '<label>system_prompt</label><div style="display:flex;gap:.3rem;align-items:center;flex-wrap:wrap"><select id="ed-sp-'+task+'" style="flex:1">'+propts(cfg.system_prompt)+'</select>'+
  '<button onclick="viewSystemPrompt(\\''+task+'\\')" title="Prompt-Inhalt anzeigen" style="background:#1e293b;border:1px solid #334155;color:#e2e8f0;cursor:pointer;padding:.15rem .5rem;border-radius:3px;font-size:.75rem">View</button>'+
  (window.__canEditLLM?'<button onclick="editSystemPrompt(\\''+task+'\\')" title="Prompt-Inhalt editieren (Premium)" style="background:#1e293b;border:1px solid #0ea5e9;color:#0ea5e9;cursor:pointer;padding:.15rem .5rem;border-radius:3px;font-size:.75rem">Edit</button>':'')+
  '<span id="ed-sp-src-'+task+'">'+_promptSourceBadge(cfg.system_prompt_source||{})+'</span>'+
  '</div>'+
  // #351 L3: faltbare Per-Provider-Override-Section
  '<label></label>'+_buildPromptByProviderSection(task,cfg.system_prompt_by_provider||{})+
  '<label>max_tokens</label><input id="ed-maxt-'+task+'" value="'+esc(cfg.max_tokens||'')+'" type="number">'+
  '<label>temperature</label><input id="ed-temp-'+task+'" value="'+esc(cfg.temperature||'')+'" type="number" step="0.1">'+
  '</div>'+
  '<div id="ed-urlerr-'+task+'" style="color:#ef4444;font-size:.75rem;margin-top:.25rem;display:none">URL erforderlich fuer diesen Provider</div>'+
  // #316: Schedule (Tag/Nacht-Switch) — Section, premium-gated
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
 if(cfg.schedule&&cfg.schedule.provider&&window.__canScheduleLLM){
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

// #316: Schedule-Section (Tag/Nacht-Switch). Premium llm_routing_advanced.
function buildScheduleSection(task,schedule){
 const can=!!window.__canScheduleLLM;
 const active=!!(schedule&&schedule.active);
 const fromV=(schedule&&schedule.from)||'22:00';
 const toV  =(schedule&&schedule.to)  ||'06:00';
 const provV=(schedule&&schedule.provider)||'';
 const modelV=(schedule&&schedule.model)||'';
 const provOpts=LLM_PROVIDERS.map(x=>'<option value="'+x+'"'+(x===provV?' selected':'')+'>'+x+'</option>').join('');
 const disabled=can?'':' disabled';
 const noteHtml=can
  ?'<span style="color:#64748b;font-size:.7rem">Mitternacht-Uebergang (z.B. 22:00 - 06:00) wird automatisch behandelt.</span>'
  :'<span style="color:#475569;font-size:.7rem">Premium-Feature <code>llm_routing_advanced</code> erforderlich</span>';
 return '<div style="margin-top:.6rem;border-top:1px dashed #334155;padding-top:.5rem">'+
  '<div style="font-weight:600;color:#e2e8f0;font-size:.85rem;margin-bottom:.3rem">Schedule (Tag/Nacht-Switch)</div>'+
  noteHtml+
  '<div style="display:grid;grid-template-columns:auto 1fr;gap:.4rem;margin-top:.3rem;max-width:560px;opacity:'+(can?'1':'0.55')+'">'+
  '<label>active</label><input type="checkbox" id="ed-sch-active-'+task+'"'+(active?' checked':'')+disabled+'>'+
  '<label>from (HH:MM)</label><input id="ed-sch-from-'+task+'" value="'+esc(fromV)+'" placeholder="22:00"'+disabled+'>'+
  '<label>to (HH:MM)</label><input id="ed-sch-to-'+task+'" value="'+esc(toV)+'" placeholder="06:00"'+disabled+'>'+
  '<label>provider</label><select id="ed-sch-prov-'+task+'" onchange="loadScheduleModels(\\''+task+'\\')"'+disabled+'><option value="">(keep current)</option>'+provOpts+'</select>'+
  '<label>model</label><select id="ed-sch-model-'+task+'"'+disabled+'><option value="'+esc(modelV)+'">'+esc(modelV||'(select provider first)')+'</option></select>'+
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
 // #328: base_url aus dem Editor-Form mitgeben — das Backend nutzt sie als
 // base_url_override, sonst baut _build_inner mit der Config-Default-URL.
 const urlEl=document.getElementById('ed-baseurl-'+task);
 const baseUrl=urlEl?urlEl.value.trim():'';
 modelEl.innerHTML='<option>(loading...)</option>';
 if(noteEl)noteEl.textContent='';
 try{
  let url='/api/v1/dashboard/llm/models?provider='+encodeURIComponent(provider);
  if(baseUrl)url+='&base_url='+encodeURIComponent(baseUrl);
  const r=await apiFetch(url);
  const j=await r.json();
  const models=(j.models||j.data&&j.data.models)||[];
  if(!models.length){
   modelEl.innerHTML='<option value="'+esc(keepModel)+'">'+esc(keepModel||'(none)')+'</option>';
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
  modelEl.innerHTML=models.map(m=>{
   const id=m.model||m.id||'';
   const prompt=m.prompt_per_1k||0;
   const completion=m.completion_per_1k||0;
   let price='';
   if(prompt>0||completion>0){
    price=' ($'+prompt.toFixed(4)+'/$'+completion.toFixed(4)+' per 1k)';
   }
   const ctx=m.context_length?' ['+(m.context_length/1000).toFixed(0)+'k ctx]':'';
   const sel=id===keepModel?' selected':'';
   return '<option value="'+esc(id)+'"'+sel+'>'+esc(id)+esc(price)+esc(ctx)+'</option>';
  }).join('');
  if(noteEl){
   noteEl.textContent=models.length+' Modelle (Preise: prompt/completion per 1k Tokens)';
  }
 }catch(err){
  modelEl.innerHTML='<option value="'+esc(keepModel)+'">'+esc(keepModel||'(error)')+'</option>';
  if(noteEl)noteEl.innerHTML='<span style="color:#ef4444">Fehler beim Laden: '+esc(String(err))+'</span>';
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
 const tm=get('ed-temp-'+task);if(tm)cfg.temperature=Number(tm);else cfg.temperature='';
 // #316: Schedule-Block — nur senden wenn die Section sichtbar/editierbar ist.
 if(window.__canScheduleLLM){
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
 }
 try{
  const r=await apiFetch('/api/v1/settings/llm/task',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task:task,config:cfg})});
  const j=await r.json();const d=j.data||j;
  if(r.ok&&d.updated){
   showToast('Saved: '+task,'ok');
   closeLLMTaskEditor(task);
   await loadSettings();
  }else{
   showToast('Fehler: '+(d.error||JSON.stringify(d)),'err');
  }
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

// #315/#338: System-Prompts View (free) + Edit-Modal (premium) mit Variante-Dropdown
function _llmPromptsModal(){
 let m=document.getElementById('prompt-modal');
 if(m)return m;
 m=document.createElement('div');
 m.id='prompt-modal';
 m.style.cssText='display:none;position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:9999;align-items:center;justify-content:center';
 m.innerHTML='<div style="background:#0f172a;border:1px solid #334155;border-radius:6px;width:80vw;max-width:900px;height:80vh;display:flex;flex-direction:column;padding:1rem">'+
  '<div id="pm-title" style="font-weight:700;font-size:1rem;margin-bottom:.5rem;color:#e2e8f0"></div>'+
  '<div id="pm-scope-row" style="display:none;font-size:.75rem;margin-bottom:.4rem;color:#94a3b8;align-items:center;gap:.4rem">'+
   '<span>Variante:</span>'+
   '<select id="pm-scope" onchange="onPromptScopeChange()" style="background:#020617;color:#e2e8f0;border:1px solid #334155;border-radius:4px;padding:.2rem .4rem;font-size:.75rem">'+
    '<option value="generic">(generic) — config/llm/prompts/&lt;name&gt;</option>'+
   '</select>'+
  '</div>'+
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

// #338 Schicht C: build the Variante-Dropdown options based on currently
// configured providers + models in the LLM-Editor. Options are: generic
// + provider:<name> for each known provider + model:<id> for each model
// the operator has currently selected per task.
//
// #351-fix: previously looked up ed-pv-/ed-md- (typo) — the actual editor
// uses ed-prov- and ed-model-, so the dropdown stayed forever stuck on
// just "(generic)" and no per-provider/-model variant could be picked.
// Also: fall back to the rows in window.__llmCfg when the inline editors
// are not currently open (modal can be triggered from any tab).
function _populateScopeDropdown(){
 const sel=document.getElementById('pm-scope');
 if(!sel)return;
 const options=['<option value="generic">(generic) — config/llm/prompts/&lt;name&gt;</option>'];
 const providers=new Set();
 const models=new Set();
 ['planning','implementation','review','healing','evaluation','default'].forEach(task=>{
  const ps=document.getElementById('ed-prov-'+task);
  if(ps&&ps.value)providers.add(ps.value.trim());
  const ms=document.getElementById('ed-model-'+task);
  if(ms&&ms.value)models.add(ms.value.trim());
 });
 // Auch persistierte Tasks beruecksichtigen, falls der Editor gerade
 // nicht geoeffnet ist (Modal kann auch von der Read-Only-Liste aus
 // gestartet werden).
 (window.__llmCfg||[]).forEach(r=>{
  if(r&&r.provider)providers.add(String(r.provider).trim());
  if(r&&r.model)models.add(String(r.model).trim());
 });
 providers.forEach(p=>{if(p)options.push('<option value="provider:'+esc(p)+'">provider: '+esc(p)+'</option>');});
 models.forEach(m=>{if(m)options.push('<option value="model:'+esc(m)+'">model: '+esc(m)+'</option>');});
 sel.innerHTML=options.join('');
}

async function onPromptScopeChange(){
 const ta=document.getElementById('pm-content');
 const name=ta.dataset.promptName||'';
 const scope=document.getElementById('pm-scope').value||'generic';
 if(!name)return;
 try{
  const r=await apiFetch('/api/v1/dashboard/llm/prompts/'+encodeURIComponent(name)+'?scope='+encodeURIComponent(scope));
  const j=await r.json();const d=j.data||j;
  let content=d.content||'';
  let isTemplate=false;
  // #351 L1: wenn an diesem Scope nichts existiert, lade die Cascade-Vorlage
  // (typischerweise package-default) damit der User direkt fein-tunen kann
  // statt von leer zu starten. Source-Indikator bleibt unverändert ehrlich.
  if(!content){
   try{
    const r2=await apiFetch('/api/v1/dashboard/llm/prompts/'+encodeURIComponent(name));
    if(r2.ok){
     const j2=await r2.json();const d2=j2.data||j2;
     if(d2.content){content=d2.content;isTemplate=true;}
    }
   }catch(e){/* silent — leeres textarea ist akzeptabler Fallback */}
  }
  ta.value=content;
  ta.dataset.promptScope=scope;
  const src=d.source||{};
  const path=src.path||'(nicht vorhanden)';
  const tplHint=isTemplate?' <span style="color:#fbbf24;font-style:italic">&middot; Vorlage aus '+esc(src.source||'package')+'</span>':'';
  document.getElementById('pm-source').innerHTML='Aktuell aktiv: '+esc(src.source||'package')+' &mdash; '+esc(path)+tplHint;
  // Reset-Button nur sichtbar wenn aktuelle Variante eine echte Operator-Override ist
  // (NICHT wenn nur die Vorlage angezeigt wird, weil dann gibt's nichts zu resetten).
  const resetBtn=document.getElementById('pm-reset');
  if(resetBtn){
   const isOperator=scope!=='generic'?((d.content||'').length>0):(src.source==='operator-generic');
   resetBtn.style.display=isOperator&&window.__canEditLLM?'inline-block':'none';
  }
 }catch(err){
  document.getElementById('pm-source').textContent='Netzwerk-Fehler: '+err;
 }
}

async function resetPromptToDefault(){
 const ta=document.getElementById('pm-content');
 const name=ta.dataset.promptName||'';
 const scope=document.getElementById('pm-scope').value||'generic';
 if(!name)return;
 if(!confirm('Operator-Override fuer "'+name+'" (Variante: '+scope+') loeschen?\\n\\nDer Lookup faellt damit auf die naechsthoehere Stufe zurueck.'))return;
 try{
  const r=await apiFetch('/api/v1/dashboard/llm/prompts/'+encodeURIComponent(name)+'?scope='+encodeURIComponent(scope),{method:'DELETE'});
  const j=await r.json();const d=j.data||j;
  if(r.ok&&d.deleted){
   showToast('Override geloescht: '+name+' ('+scope+')','ok');
   onPromptScopeChange();
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
 if(!window.__canEditLLM){showToast('Premium llm_routing_dashboard_write erforderlich','warn');return;}
 const m=_llmPromptsModal();
 document.getElementById('pm-title').textContent='Edit: '+name;
 document.getElementById('pm-source').textContent='Lade...';
 document.getElementById('pm-content').value='';
 document.getElementById('pm-content').readOnly=false;
 const ta=document.getElementById('pm-content');
 ta.dataset.promptName=name;
 ta.dataset.promptScope='generic';
 document.getElementById('pm-save').style.display='inline-block';
 document.getElementById('pm-error').style.display='none';
 // #338 Schicht C: scope-dropdown sichtbar im Edit-Mode
 _populateScopeDropdown();
 const scopeRow=document.getElementById('pm-scope-row');
 if(scopeRow)scopeRow.style.display='flex';
 const scopeSel=document.getElementById('pm-scope');
 if(scopeSel)scopeSel.value='generic';
 // #351 L2: Save-as-Input nur im Edit-Mode anzeigen + leer initialisieren
 const saveAsRow=document.getElementById('pm-saveas-row');
 if(saveAsRow)saveAsRow.style.display='flex';
 const saveAsInput=document.getElementById('pm-saveas');
 if(saveAsInput)saveAsInput.value='';
 m.style.display='flex';
 // initial Load via scope-aware Endpoint, damit Source-Indikator + Reset-Button korrekt sind
 onPromptScopeChange();
}

async function savePromptModal(){
 const ta=document.getElementById('pm-content');
 const origName=ta.dataset.promptName||'';
 const scope=document.getElementById('pm-scope')?document.getElementById('pm-scope').value:'generic';
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
  const payload={content:content};
  if(scope&&scope!=='generic')payload.scope=scope;
  const r=await apiFetch('/api/v1/dashboard/llm/prompts/'+encodeURIComponent(targetName),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const j=await r.json();const d=j.data||j;
  if(r.ok&&d.saved){
   showToast('Prompt gespeichert: '+targetName+' ('+scope+')','ok');
   // Wenn unter neuem Namen gespeichert: Modal-Inhalt auf neuen Namen umstellen
   // damit weitere Edits an der neuen Datei landen.
   if(saveAs){ta.dataset.promptName=targetName;document.getElementById('pm-title').textContent='Edit: '+targetName;saveAsEl.value='';}
   onPromptScopeChange();
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
 const scopeRow=document.getElementById('pm-scope-row');
 if(scopeRow)scopeRow.style.display='none';
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
showTab(currentTab);
</script>
</body>
</html>
"""


class SAMUELRequestHandler(BaseHTTPRequestHandler):

    def log_message(self, format: str, *args: Any) -> None:
        log.debug(format, *args)

    def _send_json(self, status: int, data: Any) -> None:
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    # Paths that are reachable without API-key auth even when auth is enabled.
    # Webhook uses HMAC, not API key. Everything else (including the HTML
    # dashboard) requires the key when SAMUEL_API_KEY is set.
    _AUTH_EXEMPT_PATHS: set[str] = {"/api/v1/webhook"}

    def _auth_required(self) -> bool:
        """Return True if the current request must be rejected as unauthorized."""
        auth = getattr(self.__class__, "auth_middleware", None)
        if auth is None:
            return False
        if self.path in self._AUTH_EXEMPT_PATHS:
            return False
        return not auth.authenticate(dict(self.headers))

    def _send_unauthorized(self) -> None:
        self._send_json(401, {"error": "unauthorized"})

    def do_GET(self) -> None:
        if self._auth_required():
            self._send_unauthorized()
            return

        if self.path == "/" or self.path == "/dashboard":
            self._send_html(DASHBOARD_HTML)
            return

        if self.path == "/api/v1/dashboard/status":
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

        if self.path == "/api/v1/dashboard/security":
            self._send_json(200, self.dashboard.get_security())
            return

        if self.path == "/api/v1/dashboard/compliance/legend":
            # #252: OWASP Top-10 Agentic AI + EU AI Act Artikel-Erklärungen
            self._send_json(200, self.dashboard.get_compliance_legend())
            return

        if self.path == "/api/v1/dashboard/workflow":
            self._send_json(200, self.dashboard.get_workflow())
            return

        if self.path.startswith("/api/v1/dashboard/workflow/"):
            tail = self.path[len("/api/v1/dashboard/workflow/"):]
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

        if self.path == "/api/v1/dashboard/llm/schedule":
            from samuel.slices.dashboard.data import get_llm_routing_schedule
            cfg = getattr(self.dashboard, "_config", None)
            cdir = "config"
            if cfg is not None:
                try:
                    cdir = str(cfg.get("agent.config_dir", "config"))
                except Exception:
                    pass
            self._send_json(200, get_llm_routing_schedule(cfg, config_dir=cdir))
            return

        # #311: OpenRouter-Models + Cache-Info
        if self.path.startswith("/api/v1/dashboard/llm/models"):
            from urllib.parse import parse_qs, urlparse

            from samuel.adapters.llm.costs import get_models_for_provider
            qs = parse_qs(urlparse(self.path).query)
            provider = (qs.get("provider") or [""])[0].lower()
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
                        provider, cfg, secrets_stub,
                        base_url_override=base_url_q or None,
                    )
                    models = adapter.list_models() if hasattr(adapter, "list_models") else []
                except Exception as exc:
                    log.warning("list_models for %s failed: %s", provider, exc)
                    models = []
            else:
                models = get_models_for_provider(provider)
            self._send_json(200, {"provider": provider, "models": models})
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
            scope_param = (qs.get("scope") or [None])[0]
            cdir = "config"
            cfg = getattr(self.dashboard, "_config", None)
            if cfg is not None:
                try:
                    cdir = str(cfg.get("agent.config_dir", "config"))
                except Exception:
                    pass

            if parsed.path == "/api/v1/dashboard/llm/prompts":
                from samuel.adapters.llm.prompts import list_available_prompts
                self._send_json(200, {
                    "prompts": list_available_prompts(cdir, scope=scope_param),
                    "scope":   scope_param or "generic",
                })
                return

            if parsed.path.startswith("/api/v1/dashboard/llm/prompts/"):
                from samuel.adapters.llm.prompts import (
                    load_prompt_at_scope,
                    load_system_prompt,
                    resolve_prompt_source,
                )
                name = parsed.path[len("/api/v1/dashboard/llm/prompts/"):]
                if not name or "/" in name or "\\" in name or ".." in name:
                    self._send_json(400, {"error": "invalid prompt name"})
                    return
                # When scope is given, load only that specific override (no
                # cascade fallback) so the modal shows what is actually
                # written there. Otherwise: legacy cascade load.
                if scope_param:
                    content = load_prompt_at_scope(name, cdir, scope=scope_param)
                    src_info = resolve_prompt_source(name, cdir)
                    self._send_json(200, {
                        "name":    name,
                        "content": content,  # may be empty when no override at this scope
                        "scope":   scope_param,
                        "source":  src_info,
                    })
                    return
                content = load_system_prompt(name, cdir)
                if not content:
                    self._send_json(404, {"error": f"prompt not found: {name}"})
                    return
                src_info = resolve_prompt_source(name, cdir)
                self._send_json(200, {
                    "name":    name,
                    "content": content,
                    "source":  src_info,
                })
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
        if self._auth_required():
            self._send_unauthorized()
            return
        # Minimal HEAD: say 200 for known GET-paths, else 404
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_POST(self) -> None:
        if self._auth_required():
            self._send_unauthorized()
            return

        body = self._read_body()

        if self.path == "/api/v1/webhook":
            event_type = self.headers.get("X-Gitea-Event", "") or self.headers.get("X-GitHub-Event", "")
            signature = self.headers.get("X-Gitea-Signature", "") or self.headers.get("X-Hub-Signature-256", "")
            resp = self.webhook_adapter.handle_webhook(event_type, body, signature)
            self._send_json(resp.get("status", 200), resp)
            return

        # #315/#338: Prompts-Write (Premium llm_routing_dashboard_write)
        if self.path.startswith("/api/v1/dashboard/llm/prompts/"):
            from samuel.adapters.llm.prompts import write_prompt
            name = self.path[len("/api/v1/dashboard/llm/prompts/"):]
            content = (body or {}).get("content", "")
            scope = (body or {}).get("scope")
            cdir = "config"
            cfg = getattr(self.dashboard, "_config", None)
            if cfg is not None:
                try:
                    cdir = str(cfg.get("agent.config_dir", "config"))
                except Exception:
                    pass
            result = write_prompt(name, content, cdir, scope=scope)
            self._send_json(200 if result.get("saved") else 400, result)
            return

        resp = self.rest_api.handle_request("POST", self.path, body=body, headers=dict(self.headers))
        self._send_json(resp.get("status", 200), resp.get("data", resp))

    def do_DELETE(self) -> None:  # noqa: N802
        if self._auth_required():
            self._send_unauthorized()
            return

        # #338 Schicht C: Reset-to-Default — entfernt einen Operator-Override.
        if self.path.startswith("/api/v1/dashboard/llm/prompts/"):
            from urllib.parse import parse_qs, urlparse

            from samuel.adapters.llm.prompts import delete_prompt
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            scope_param = (qs.get("scope") or [None])[0]
            name = parsed.path[len("/api/v1/dashboard/llm/prompts/"):]
            if not name or "/" in name or "\\" in name or ".." in name:
                self._send_json(400, {"error": "invalid prompt name"})
                return
            cdir = "config"
            cfg = getattr(self.dashboard, "_config", None)
            if cfg is not None:
                try:
                    cdir = str(cfg.get("agent.config_dir", "config"))
                except Exception:
                    pass
            result = delete_prompt(name, cdir, scope=scope_param)
            self._send_json(200 if result.get("deleted") else 400, result)
            return

        self._send_json(404, {"error": "not found"})


def create_server(
    bus: Bus,
    host: str = "0.0.0.0",
    port: int = 7777,
    scm: Any = None,
    config: Any = None,
) -> HTTPServer:
    api_key = os.environ.get("SAMUEL_API_KEY", "")
    if api_key:
        _auth = APIKeyAuth([api_key])
        log.info("API key auth enabled for /api/* endpoints")
    else:
        _auth = None
        log.warning("SAMUEL_API_KEY not set — API endpoints have NO authentication")
    webhook_secret = os.environ.get("SLICE_HMAC_KEY", "")
    _webhooks = WebhookIngressAdapter(bus, secret=webhook_secret)
    # Build transfer warning function from privacy config
    transfer_warning_fn = None
    try:
        from pathlib import Path as _Path

        from samuel.slices.privacy.handler import TransferWarning
        _privacy_path = _Path("config/privacy.json")
        if _privacy_path.exists():
            _privacy_data = json.loads(_privacy_path.read_text(encoding="utf-8"))
        else:
            _privacy_data = {}
        _tw = TransferWarning(_privacy_data)
        transfer_warning_fn = _tw.check_all_providers
    except Exception as e:
        log.warning("Failed to load transfer warning config: %s", e)
    # #311-followup: balance_resolver wird hier (Wiring-Layer) gebaut, weil
    # samuel/slices/dashboard/* die Adapter-Imports nicht haben darf
    # (test_no_direct_adapter_usage). Server-py ist nicht in slices/.
    _PROVIDERS_WITH_BALANCE_API = frozenset({"deepseek", "openrouter"})

    def _balance_resolver(
        provider: str, env_key: str | None, url: str | None,
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
                prov, cfg_stub, secrets_stub,
                model_override=cfg.get("model"),
                base_url_override=cfg.get("base_url"),
                timeout_override=int(cfg["timeout"]) if cfg.get("timeout") else None,
            )
            result = adapter.validate()
            return {
                "valid":   bool(result.get("valid")),
                "detail":  str(result.get("detail", "")),
                "balance": result.get("balance"),
            }
        except Exception as exc:
            log.warning("test_connection for %s failed: %s", prov, exc)
            return {"valid": False, "detail": f"test failed: {exc}", "balance": None}

    # #348: prompt_source_resolver — Wiring-Schicht darf den Adapter
    # direkt importieren; die Slice (data.py) darf das nicht. Damit kann
    # der Editor pro Task ausweisen, welche Cascade-Stufe gerade greift
    # (package / operator-generic / operator-provider:X / operator-model:Y).
    from samuel.adapters.llm.prompts import resolve_prompt_source

    def _prompt_source_resolver(
        name: str, cdir: str,
        provider: str | None, model: str | None,
        by_provider: dict | None = None,
    ) -> dict:
        return resolve_prompt_source(
            name, cdir, provider=provider, model=model,
            by_provider=by_provider,
        )

    _dash = DashboardHandler(
        bus, scm=scm, config=config,
        transfer_warning_fn=transfer_warning_fn,
        balance_resolver=_balance_resolver,
        connection_tester=_connection_tester,
        prompt_source_resolver=_prompt_source_resolver,
    )
    _setup = SetupHandler(bus, config=config, scm=scm)
    _rest = RestAPI(bus, auth_middleware=_auth, setup_handler=_setup, dashboard_handler=_dash)

    class Handler(SAMUELRequestHandler):
        rest_api = _rest
        webhook_adapter = _webhooks
        dashboard = _dash
        auth_middleware = _auth

    server = HTTPServer((host, port), Handler)
    log.info("HTTP-Server auf %s:%d", host, port)
    return server
