"""Integration tests for the Phase 14.6 dashboard server wiring.

Covers:
- HTML + /api/* routes require API key when SAMUEL_API_KEY is set
- No auth in dev-mode (SAMUEL_API_KEY not set)
- /api/v1/dashboard/self_check returns checks list
- /api/v1/setup/labels reachable via RestAPI (delegates to SetupHandler)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from html.parser import HTMLParser
from http.server import HTTPServer
from pathlib import Path

import pytest

from samuel import __build_info__, __version__
from samuel.core.bus import Bus
from samuel.core.commands import HealthCheckCommand
from samuel.core.events import Event
from samuel.server import DASHBOARD_HTML, create_server, render_dashboard_html


def _suggestion_script():
    import tree_sitter_javascript
    from tree_sitter import Language, Parser

    names = {
        b"buildScheduleSection",
        b"openLLMTaskEditor",
        b"modelSuggestionFields",
        b"loadModelsForProvider",
        b"loadScheduleModels",
        b"loadSetupModels",
        b"updateModelAssessment",
        b"updateSetupModelAssessment",
        b"refreshVisibleModelSuggestions",
        b"refreshOpenRouterCache",
        b"renderModelCacheStatus",
    }
    collector = _InlineScriptCollector()
    collector.feed(DASHBOARD_HTML)
    parser = Parser(Language(tree_sitter_javascript.language()))
    functions = []
    for script in collector.scripts:
        for statement in parser.parse(script.encode()).root_node.named_children:
            name = statement.child_by_field_name("name")
            if statement.type == "function_declaration" and name and name.text in names:
                functions.append((statement.text or b"").decode())
    assert len(functions) == len(names)
    return "\n".join(functions)


def _run_suggestion_ui(scenario, body):
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the UI behavior regression")
    harness = r"""
const scenario=JSON.parse(require('fs').readFileSync(0,'utf8'));
const elements=new Map();
const document={getElementById(id){return elements.get(id)||null;}};
const esc=value=>String(value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
const fmt=String,fmtTime=String,showToast=()=>{};
let setupLoaded=true;
const window={__llmCfg:[{task:'planning',model:'custom-unknown-model',schedule:{active:true,provider:'openrouter',model:'saved-schedule-model'}}]};
const LLM_PROVIDERS=['openrouter','ollama'],LLM_PROMPTS=[''];
const _ensurePromptListLoaded=async()=>{},loadPromptsForTask=()=>{},onLLMProviderChange=()=>{};
const _promptSourceBadge=()=>'',_buildPromptByProviderSection=()=>'';
function make(id,value=''){
 const el={value,innerHTML:'',textContent:'',style:{display:'block'},dataset:{},
 get options(){return Array.from(this.innerHTML.matchAll(/<option value="([^"]*)" data-assessment="([^"]*)">/g),m=>({value:m[1],dataset:{assessment:m[2]}}));}};
 elements.set(id,el);return el;
}
for(const surface of ['task','schedule','setup']){
 const ids=modelSuggestionFields('planning',surface);
 for(const key of ['provider','model','list','note','url'])if(!elements.has(ids[key]))make(ids[key]);
 document.getElementById(ids.provider).value='openrouter';
 document.getElementById(ids.model).value='custom-unknown-model';
}
make('llm-edit-planning');make('l-model-cache');
const pending=[],requests=[];
function apiFetch(url,options){requests.push({url,options});return new Promise((resolve,reject)=>pending.push({resolve,reject,url}));}
function response(models=[],ok=true,cache={status:'fresh'}){return {ok,status:ok?200:503,json:async()=>({models,cache})};}
function view(surface){
 const ids=modelSuggestionFields('planning',surface);
 return {value:document.getElementById(ids.model).value,html:document.getElementById(ids.list).innerHTML,note:document.getElementById(ids.note).textContent};
}
"""
    result = subprocess.run(
        [node, "-e", _suggestion_script() + harness + body],
        input=json.dumps(scenario),
        text=True,
        capture_output=True,
        check=True,
        timeout=5,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("surface", ["task", "schedule", "setup"])
@pytest.mark.parametrize("status", ["fresh", "stale", "missing", "unreadable", "upgrade_required"])
def test_model_editors_render_nonempty_response_with_own_cache_metadata(surface, status):
    observed = _run_suggestion_ui(
        {"surface": surface, "status": status},
        r"""
(async()=>{
 const job=loadModelsForProvider('planning',undefined,scenario.surface);
 pending[0].resolve(response([{id:'vendor/current-model',suitability:{available:false}}],true,{status:scenario.status}));
 await job;process.stdout.write(JSON.stringify({view:view(scenario.surface),requests}));
})().catch(error=>{process.stderr.write(String(error));process.exitCode=1;});
""",
    )
    assert observed["view"]["value"] == "custom-unknown-model"
    assert 'value="vendor/current-model"' in observed["view"]["html"]
    assert status in observed["view"]["note"]
    assert "Provider-/Kontoverfügbarkeit unbekannt" in observed["view"]["note"]
    assert "provider=openrouter" in observed["requests"][0]["url"]
    assert "options" not in observed["requests"][0]


@pytest.mark.parametrize("surface", ["task", "schedule", "setup"])
@pytest.mark.parametrize(
    "case",
    [
        "empty",
        "network",
        "http",
        "removed",
        "race_success",
        "race_error",
        "closed",
        "typing",
        "endpoint",
    ],
)
def test_model_discovery_preserves_free_input_and_ignores_stale_response(surface, case):
    observed = _run_suggestion_ui(
        {"surface": surface, "case": case},
        r"""
(async()=>{
 const surface=scenario.surface,ids=modelSuggestionFields('planning',surface);
 const first=loadModelsForProvider('planning',undefined,surface);
 let prior=null;
 if(scenario.case.startsWith('race')){
  document.getElementById(ids.provider).value='deepseek';
  const second=loadModelsForProvider('planning',undefined,surface);
  pending[1].resolve(response([{id:'second-model'}]));await second;prior=view(surface);
 }else if(scenario.case==='closed'){
  elements.delete(ids.model);make(ids.model,'new-editor-model');prior=view(surface);
 }else if(scenario.case==='typing'){
  document.getElementById(ids.model).value='typed-during-request';
 }else if(scenario.case==='endpoint'){
  document.getElementById(ids.url).value='http://different-endpoint.test';prior=view(surface);
 }
 if(['network','race_error'].includes(scenario.case))pending[0].reject(new Error('network unavailable'));
 else pending[0].resolve(response(scenario.case==='empty'?[]:[{id:'first-model'}],scenario.case!=='http'));
 await first;process.stdout.write(JSON.stringify({prior,after:view(surface),requests}));
})().catch(error=>{process.stderr.write(String(error));process.exitCode=1;});
""",
    )
    after = observed["after"]
    if case.startswith("race") or case in {"closed", "endpoint"}:
        assert after == observed["prior"]
    else:
        assert after["value"] == (
            "typed-during-request" if case == "typing" else "custom-unknown-model"
        )
        assert "UNKNOWN" in after["note"]
        if case in {"network", "http"}:
            assert "nicht erreichbar" in after["note"]
            assert "first-model" not in after["html"]
        elif case == "removed":
            assert 'value="first-model"' in after["html"]
    assert all("options" not in request for request in observed["requests"])


def test_setup_local_discovery_is_explicit_and_does_not_change_input():
    observed = _run_suggestion_ui(
        {},
        r"""
(async()=>{
 make('setup-llm-provider','ollama');make('setup-llm-base-url','http://local.test:11434');
 await loadSetupModels();const passive=view('setup'),before=requests.length;
 const active=loadSetupModels(true);pending[0].resolve(response([{id:'installed-local-model'}]));await active;
 process.stdout.write(JSON.stringify({passive,before,active:view('setup'),requests}));
})().catch(error=>{process.stderr.write(String(error));process.exitCode=1;});
""",
    )
    assert observed["before"] == 0
    assert "noch nicht abgefragt" in observed["passive"]["note"]
    assert observed["active"]["value"] == "custom-unknown-model"
    assert "Endpointliste" in observed["active"]["note"]
    assert "base_url=http%3A%2F%2Flocal.test%3A11434" in observed["requests"][0]["url"]


@pytest.mark.parametrize("failed", [False, True])
def test_catalog_refresh_updates_all_open_forms_without_model_replacement(failed):
    observed = _run_suggestion_ui(
        {"failed": failed},
        r"""
(async()=>{
 const cache={status:'fresh',benchmark_count:0,benchmark_error:'HTTPError:403'};
 async function loadLLMStub(){renderModelCacheStatus(document.getElementById('l-model-cache'),cache);}
 globalThis.loadLLM=loadLLMStub;
 const stale=loadModelsForProvider('planning');
 const refresh=refreshOpenRouterCache();
 if(scenario.failed)pending[1].reject(new Error('unreachable'));
 else pending[1].resolve({ok:true,json:async()=>({count:1,benchmark_count:0,benchmark_error:'HTTPError:403'})});
 for(let i=0;i<8;i++)await Promise.resolve();
 for(const request of pending.slice(2))request.resolve(response([{id:'new-generation-model'}],true,cache));
 try{await refresh;}catch(error){}
 pending[0].resolve(response([{id:'old-generation-model'}]));await stale;
 process.stdout.write(JSON.stringify({views:['task','schedule','setup'].map(view),panel:document.getElementById('l-model-cache').innerHTML,requests}));
})().catch(error=>{process.stderr.write(String(error));process.exitCode=1;});
""",
    )
    assert len(observed["requests"]) == 5
    assert observed["requests"][1]["options"] == {"method": "POST"}
    for view in observed["views"]:
        assert view["value"] == "custom-unknown-model"
        assert "new-generation-model" in view["html"]
        assert "old-generation-model" not in view["html"]
        if failed:
            assert "Letzte Katalogaktualisierung fehlgeschlagen" in view["note"]
    if not failed:
        assert "Modellkatalog: aktuell" in observed["panel"]
        assert "Benchmarks:</strong> nicht verfügbar (UNKNOWN)" in observed["panel"]
        assert "Provider-/Kontoverfügbarkeit bleibt unbekannt" in observed["panel"]


def test_model_suggestions_escape_untrusted_ids_and_benchmark_errors():
    observed = _run_suggestion_ui(
        {},
        r"""
(async()=>{
 const job=loadModelsForProvider('planning');pending[0].resolve(response([{id:'<script>bad</script>'}]));await job;
 renderModelCacheStatus(document.getElementById('l-model-cache'),{status:'fresh',benchmark_error:'<img src=x onerror=bad>'});
 process.stdout.write(JSON.stringify({view:view('task'),panel:document.getElementById('l-model-cache').innerHTML}));
})().catch(error=>{process.stderr.write(String(error));process.exitCode=1;});
""",
    )
    assert "<script>" not in observed["view"]["html"]
    assert "<img src=x" not in observed["panel"]
    assert "&lt;script>" in observed["view"]["html"]


def test_llm_activity_http_reads_bound_runtime_without_workflow_effects():
    bus = Bus()
    events: list[Event] = []
    bus.subscribe("*", events.append)
    bus.llm_activity_resolver = lambda: {
        "status": "idle",
        "calls": [],
        "last_call": {
            "task": "review",
            "provider": "deepseek",
            "model": "actual-model",
            "outcome": "response_received",
            "started_at": "2026-10-04T07:49:00+00:00",
            "finished_at": "2026-10-04T07:49:40.754394+00:00",
        },
    }
    srv = create_server(bus, host="127.0.0.1", port=0, authentication=False)
    with (
        _serve(srv),
        urllib.request.urlopen(_url(srv, "/api/v1/dashboard/llm"), timeout=2) as response,
    ):
        result = json.loads(response.read())
    data = result.get("data", result)
    assert data["activity"]["status"] == "idle"
    assert data["activity"]["last_call"]["model"] == "actual-model"
    assert data["activity"]["last_call"]["finished_at"] == "2026-10-04T07:49:40.754394+00:00"
    assert events == []
    assert "Konfigurierter Default-Provider" in DASHBOARD_HTML
    assert "kein Parser-, Task-, Gate- oder Qualification-PASS" in DASHBOARD_HTML


def test_webhook_verifies_native_gitea_signature_against_raw_request_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "native-gitea-test-secret"
    monkeypatch.setenv("SLICE_HMAC_KEY", secret)
    bus = Bus()
    srv = create_server(bus, host="127.0.0.1", port=0, authentication=False)
    raw_body = b'{\n  "private": "raw-spacing-matters"\n}'
    signature = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    request = urllib.request.Request(
        _url(srv, "/api/v1/webhook"),
        data=raw_body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Gitea-Event": "unknown",
            "X-Gitea-Event-Type": "unknown",
            "X-Gitea-Delivery": "server-raw-body-test",
            "X-Gitea-Signature": signature,
        },
    )

    with _serve(srv):
        response = urllib.request.urlopen(request, timeout=2)
        result = json.loads(response.read())

    assert response.status == 200
    assert result["action"] == "ignored"


def test_long_webhook_keeps_dashboard_and_mutating_health_reachable() -> None:
    entered = threading.Event()
    release = threading.Event()
    webhook_calls = []
    health_calls = []
    workflow_events: list[Event] = []

    class BlockingWebhook:
        def handle_webhook(self, *_args, **_kwargs):
            webhook_calls.append(1)
            entered.set()
            assert release.wait(4)
            return {"status": 202, "action": "handled"}

    bus = Bus()

    def health(command: HealthCheckCommand) -> dict[str, bool]:
        health_calls.append(command)
        return {"healthy": True}

    bus.register_command("HealthCheck", health)
    bus.subscribe("*", workflow_events.append)
    srv = create_server(bus, host="127.0.0.1", port=0, authentication=False)
    srv.RequestHandlerClass.webhook_adapter = BlockingWebhook()
    request = urllib.request.Request(
        _url(srv, "/api/v1/webhook"),
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    with _serve(srv), ThreadPoolExecutor(max_workers=2) as pool:
        webhook = pool.submit(lambda: urllib.request.urlopen(request, timeout=5).read())
        try:
            assert entered.wait(2)
            for path in (
                "/api/v1/dashboard/workflow",
                "/api/v1/dashboard/status",
                "/api/v1/health",
            ):
                with urllib.request.urlopen(_url(srv, path), timeout=2) as response:
                    assert response.status == 200
                    assert isinstance(json.loads(response.read()), dict)
            assert not webhook.done()
        finally:
            release.set()
        assert json.loads(webhook.result(timeout=3))["action"] == "handled"

    assert len(webhook_calls) == 1
    assert len(health_calls) == 1  # The existing Health API dispatches a command.
    assert workflow_events == []  # Dashboard reads do not dispatch workflow events.


class _InlineScriptCollector(HTMLParser):
    """Collect inline JavaScript exactly as browsers receive it."""

    def __init__(self) -> None:
        super().__init__()
        self._inline_script = False
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        self._inline_script = not any(name.lower() == "src" for name, _ in attrs)
        if self._inline_script:
            self.scripts.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script":
            self._inline_script = False

    def handle_data(self, data: str) -> None:
        if self._inline_script:
            self.scripts[-1] += data


class _DashboardSurfaceCollector(HTMLParser):
    """Collect the stable operator-facing dashboard tab contract."""

    def __init__(self) -> None:
        super().__init__()
        self.navigation_tabs: set[str] = set()
        self.content_tabs: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        element_id = attributes.get("id") or ""
        onclick = attributes.get("onclick") or ""

        if tag.lower() == "button" and "tab" in classes:
            prefix = "showTab('"
            suffix = "')"
            if onclick.startswith(prefix) and onclick.endswith(suffix):
                self.navigation_tabs.add(onclick[len(prefix) : -len(suffix)])
        if tag.lower() == "div" and "tab-content" in classes and element_id.startswith("tab-"):
            self.content_tabs.add(element_id.removeprefix("tab-"))


def _unescaped_string_linebreak(script: str) -> tuple[int, int] | None:
    """Return the first raw line break in a normal JavaScript string.

    JavaScript comments and template literals are separate lexical contexts;
    line breaks there are valid and must not create false positives. Escaped
    line continuations in single- and double-quoted strings are valid too.
    """

    state = "code"
    line = 1
    column = 1
    index = 0
    while index < len(script):
        char = script[index]
        following = script[index + 1] if index + 1 < len(script) else ""

        if state in {"single", "double", "template"} and char == "\\":
            if following == "\r" and index + 2 < len(script) and script[index + 2] == "\n":
                index += 3
                line += 1
                column = 1
            elif following in {"\r", "\n"}:
                index += 2
                line += 1
                column = 1
            else:
                index += 2
                column += 2
            continue

        if state in {"single", "double"}:
            if char in {"\r", "\n"}:
                return line, column
            expected = "'" if state == "single" else '"'
            if char == expected:
                state = "code"
        elif state == "template":
            if char == "`":
                state = "code"
        elif state == "line_comment":
            if char in {"\r", "\n"}:
                state = "code"
        elif state == "block_comment":
            if char == "*" and following == "/":
                index += 2
                column += 2
                state = "code"
                continue
        elif char == "/" and following == "/":
            state = "line_comment"
            index += 2
            column += 2
            continue
        elif char == "/" and following == "*":
            state = "block_comment"
            index += 2
            column += 2
            continue
        elif char == "'":
            state = "single"
        elif char == '"':
            state = "double"
        elif char == "`":
            state = "template"

        if char == "\n":
            line += 1
            column = 1
        elif char == "\r":
            if following != "\n":
                line += 1
                column = 1
        else:
            column += 1
        index += 1
    return None


@contextmanager
def _serve(srv: HTTPServer):
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()


def _url(srv: HTTPServer, path: str) -> str:
    host, port = srv.server_address[:2]
    # host may be bytes/0.0.0.0 — normalise
    host_str = "127.0.0.1" if str(host) in ("0.0.0.0", "", "b''") else str(host)
    return f"http://{host_str}:{port}{path}"


class TestServerAuthEnabled:
    def test_dashboard_html_served_without_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # #402: Die HTML-Shell ist bewusst auth-frei (sonst kommt der Browser nie
        # an die Seite, um den Key einzugeben). Daten bleiben ueber /api/* geschuetzt
        # (siehe test_api_dashboard_endpoints_require_auth). Das JS fragt bei 401
        # nach dem Key.
        monkeypatch.setenv("SAMUEL_API_KEY", "secret-xyz")
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0)
        with _serve(srv):
            resp = urllib.request.urlopen(_url(srv, "/"), timeout=2)
            assert resp.status == 200
            assert b"S.A.M.U.E.L." in resp.read()
            resp2 = urllib.request.urlopen(_url(srv, "/dashboard"), timeout=2)
            assert resp2.status == 200

    def test_api_dashboard_endpoints_require_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SAMUEL_API_KEY", "abc-123")
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0)
        with _serve(srv):
            req = urllib.request.Request(_url(srv, "/api/v1/dashboard/status"))
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req, timeout=2)
            assert exc_info.value.code == 401

            req2 = urllib.request.Request(
                _url(srv, "/api/v1/dashboard/status"),
                headers={"Authorization": "Bearer abc-123"},
            )
            resp = urllib.request.urlopen(req2, timeout=2)
            assert resp.status == 200

    def test_auth_check_validates_key_immediately(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SAMUEL_API_KEY", "abc-123")
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0)
        with _serve(srv):
            bad = urllib.request.Request(
                _url(srv, "/api/v1/auth/check"),
                headers={"X-API-Key": "wrong"},
            )
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(bad, timeout=2)
            assert exc_info.value.code == 401

            good = urllib.request.Request(
                _url(srv, "/api/v1/auth/check"),
                headers={"X-API-Key": "abc-123"},
            )
            response = urllib.request.urlopen(good, timeout=2)
            assert response.status == 200
            assert json.loads(response.read()) == {
                "authenticated": True,
                "auth_required": True,
            }

    def test_dashboard_html_has_immediate_shared_login_flow(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SAMUEL_API_KEY", "abc-123")
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0)
        with _serve(srv):
            html = urllib.request.urlopen(_url(srv, "/"), timeout=2).read().decode()
        assert "/api/v1/auth/check" in html
        assert "API-Key akzeptiert" in html
        assert "authPromptPromise" in html
        assert 'id="auth-overlay"' in html
        assert 'id="auth-key" type="password"' in html
        assert "SAMUEL_API_KEY" in html
        assert "nur für diesen Browser-Tab" in html
        assert "API-Key vergessen" not in html
        assert "forgetApiKey" not in html
        assert "prompt('API-Key" not in html
        assert "bp.error==='permission_denied'" in html
        assert "EINGESCHRAENKT" in html
        assert 'id="theme-toggle"' in html
        assert "samuel-theme" in html
        assert 'html[data-theme="light"]' in html
        assert "localStorage.setItem('samuel-theme',normalized)" in html
        assert "aria-pressed" in html
        assert "/api/v1/settings/llm/global" in html
        assert "Default/Fallback gespeichert" in html
        assert "/api/v1/dashboard/llm/models/refresh" in html
        assert "Modell- und Benchmarkdaten aktualisieren" in html
        assert "0 = keine explizite Steuerung" in html
        assert "Provider-Default · 0 ist nicht „aus“" in html
        assert "data-assessment" in html
        assert "Reasoning: ja" in html
        assert "Qualität: keine Daten" in html
        assert "updateModelAssessment" in html
        assert 'id="tab-problems"' in html
        assert "/api/v1/dashboard/problems" in html
        assert 'id="prob-debug"' in html
        assert 'id="tab-setup"' in html
        assert "/api/v1/setup/status" in html
        assert "/api/v1/setup/configure" in html
        assert 'type="password"' in html


class TestServerDevMode:
    @pytest.mark.parametrize("path", ["/", "/dashboard"])
    def test_dashboard_version_is_visible_before_auth_and_matches_status(
        self, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        monkeypatch.setenv("SAMUEL_API_KEY", "version-test-key")
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0)
        with _serve(srv):
            shell_response = urllib.request.urlopen(_url(srv, path), timeout=2)
            html = shell_response.read().decode()
            cache_control = shell_response.headers.get("Cache-Control")
            request = urllib.request.Request(
                _url(srv, "/api/v1/dashboard/status"),
                headers={"X-API-Key": "version-test-key"},
            )
            response = urllib.request.urlopen(request, timeout=2)
            status = json.loads(response.read())

        assert status["build"] == __build_info__.as_dict()
        assert status["build"]["product_version"] == __version__
        assert f'id="product-version">{__version__}</span>' in html
        assert cache_control == "no-store"
        if __build_info__.revision:
            assert __build_info__.revision not in html
        assert "v2.0.0-alpha" not in html
        assert "build.product_version" in html
        assert "build.revision" in html

    def test_dashboard_template_has_no_hardcoded_current_product_version(self) -> None:
        assert "__SAMUEL_PRODUCT_VERSION__" in DASHBOARD_HTML
        assert "2.0.0-alpha" not in DASHBOARD_HTML
        assert "2.0.0a0" not in DASHBOARD_HTML
        assert "2.0.0a1" not in DASHBOARD_HTML

    def test_dashboard_version_rendering_escapes_metadata_and_has_honest_fallback(
        self,
    ) -> None:
        rendered = render_dashboard_html('<script data-secret="x">')

        assert '<script data-secret="x">' not in rendered
        assert "&lt;script data-secret=&quot;x&quot;&gt;" in rendered
        assert 'id="product-version">0+unknown</span>' in render_dashboard_html("")

    def test_legacy_mode_fails_closed_when_key_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        with pytest.raises(ValueError, match="requires SAMUEL_API_KEY"):
            create_server(bus, host="127.0.0.1", port=0)

    def test_first_run_setup_persists_for_restart_without_hot_reload(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        from unittest.mock import MagicMock

        for key in (
            "SCM_PROVIDER",
            "SCM_URL",
            "SCM_TOKEN",
            "SCM_REPO",
            "SCM_REQUIRED_STATUS_CONTEXT",
            "SAMUEL_API_KEY",
            "SLICE_HMAC_KEY",
            "SAMUEL_AUDIT_HMAC_KEY",
            "DEEPSEEK_API_KEY",
        ):
            monkeypatch.delenv(key, raising=False)
        config = MagicMock()
        config.get.side_effect = lambda key, default=None: (
            str(tmp_path / "config") if key == "agent.config_dir" else default
        )
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(
            bus,
            host="127.0.0.1",
            port=0,
            config=config,
            setup_scm_tester=lambda *_args: {"valid": True, "detail": "ok"},
            setup_llm_tester=lambda *_args: {"valid": True, "detail": "ok"},
            configuration_mode="setup",
            authentication=False,
        )
        payload = {
            "scm_provider": "gitea",
            "scm_url": "https://gitea.example.test",
            "scm_token": "scm-secret",
            "scm_repo": "owner/repo",
            "scm_required_status_context": "CI / demo-tests (pull_request)",
            "dashboard_port": "7777",
            "llm_provider": "deepseek",
            "llm_api_key": "llm-secret",
            "llm_model": "unknown-manually-entered-model",
        }
        with _serve(srv):
            status = urllib.request.urlopen(_url(srv, "/api/v1/setup/status"), timeout=2)
            assert json.loads(status.read())["first_run"] is True
            request = urllib.request.Request(
                _url(srv, "/api/v1/setup/configure"),
                data=json.dumps(payload).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            result = json.loads(urllib.request.urlopen(request, timeout=2).read())
            key = result["api_key"]
            assert result["configured"] is True
            assert key

            final = json.loads(
                urllib.request.urlopen(_url(srv, "/api/v1/setup/status"), timeout=2).read()
            )
            assert final["values"]["scm_required_status_context"] == (
                "CI / demo-tests (pull_request)"
            )
            assert final["values"]["scm_required_status_context_source"] == "configured"
            assert final["values"]["llm_model"] == "unknown-manually-entered-model"
            assert final["first_run"] is False
            assert "scm-secret" not in json.dumps(final)
            assert "llm-secret" not in json.dumps(final)

        assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
        assert (tmp_path / "config" / "llm.json").exists()

    def test_setup_write_is_denied_remotely_without_auth(self) -> None:
        from samuel.server import SAMUELRequestHandler

        handler = object.__new__(SAMUELRequestHandler)
        handler.client_address = ("192.0.2.20", 12345)
        assert handler._setup_access_allowed() is False
        handler.client_address = ("127.0.0.1", 12345)
        assert handler._setup_access_allowed() is True

    def test_problems_endpoint_returns_filterable_shape(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        from unittest.mock import MagicMock

        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        config = MagicMock()
        config.get.side_effect = lambda key, default=None: (
            str(tmp_path) if key == "agent.data_dir" else default
        )
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0, config=config, authentication=False)

        with _serve(srv):
            response = urllib.request.urlopen(_url(srv, "/api/v1/dashboard/problems"), timeout=2)
            body = json.loads(response.read())

        assert body == {
            "problems": [],
            "counts": {"error": 0, "warn": 0, "historical": 0},
        }


class TestSelfCheckRoute:
    def test_self_check_endpoint_returns_checks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        bus = Bus()
        bus.register_command(
            "HealthCheck",
            lambda cmd: {
                "healthy": True,
                "checks": {"python": {"passed": True, "version": "3.12"}},
            },
        )
        srv = create_server(bus, host="127.0.0.1", port=0, authentication=False)
        with _serve(srv):
            import json as _json

            resp = urllib.request.urlopen(_url(srv, "/api/v1/dashboard/self_check"), timeout=2)
            body = _json.loads(resp.read())
            assert body["healthy"] is True
            assert any(c["name"] == "python" for c in body["checks"])

    def test_health_endpoint_matches_real_health_handler_contract(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        from unittest.mock import MagicMock

        from samuel.adapters.state.sqlite import SQLiteStateStore
        from samuel.slices.health.handler import HealthHandler

        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        bus = Bus()
        state = SQLiteStateStore(tmp_path)
        bus.state_store = state
        bus.run_projection_store = state.projections
        scm = MagicMock()
        scm.list_issues.return_value = []
        config = MagicMock()
        config.get.side_effect = lambda key, default=None: default
        health_handler = HealthHandler(
            bus,
            scm=scm,
            llm=None,
            config=config,
            state=state,
            projection_store=state.projections,
        )
        bus.register_command("HealthCheck", health_handler.handle)
        health_handler.handle(HealthCheckCommand())
        scm.reset_mock()
        srv = create_server(
            bus,
            host="127.0.0.1",
            port=0,
            scm=scm,
            config=config,
            authentication=False,
        )

        with _serve(srv):
            response = urllib.request.urlopen(
                _url(srv, "/api/v1/dashboard/health"),
                timeout=2,
            )
            body = json.loads(response.read())

        assert body["healthy"] is False
        assert body["checks"] == {
            "python": True,
            "git": True,
            "config": True,
            "execution_provider": True,
            "scm": True,
            "llm": False,
            "state": True,
            "authority": True,
        }
        assert body["passive"] is True
        scm.list_issues.assert_not_called()


class TestSettingsFlagRoute:
    def test_production_mode_rejects_flag_before_mutation(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        from samuel.core.config import FileConfig

        (tmp_path / "agent.json").write_text(
            json.dumps({"config_dir": str(tmp_path)}), encoding="utf-8"
        )
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        cfg = FileConfig(tmp_path)
        srv = create_server(bus, host="127.0.0.1", port=0, config=cfg, authentication=False)
        with _serve(srv):
            req = urllib.request.Request(
                _url(srv, "/api/v1/settings/flag"),
                data=json.dumps({"name": "eval", "enabled": True}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req, timeout=2)
            body = json.loads(exc_info.value.read())

        assert exc_info.value.code == 409
        assert body["code"] == "configuration_frozen"
        assert not (tmp_path / "features.json").exists()

    def test_setup_mode_persists_flag_for_restart(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        from samuel.core.config import FileConfig

        (tmp_path / "agent.json").write_text(
            json.dumps({"config_dir": str(tmp_path)}), encoding="utf-8"
        )
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        cfg = FileConfig(tmp_path)
        srv = create_server(
            bus,
            host="127.0.0.1",
            port=0,
            config=cfg,
            configuration_mode="setup",
            authentication=False,
        )
        with _serve(srv):
            import json as _json

            data = _json.dumps({"name": "eval", "enabled": True}).encode()
            req = urllib.request.Request(
                _url(srv, "/api/v1/settings/flag"),
                data=data,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=2)
            body = _json.loads(resp.read())
            assert body.get("updated") is True
            assert cfg.feature_flag("eval") is False
            assert _json.loads((tmp_path / "features.json").read_text())["eval"] is True


class TestLLMModelsRoute:
    """#328: /api/v1/dashboard/llm/models must use base_url query param so the
    LLM-Editor can show models for a remote LMStudio/Ollama instance."""

    def _make_config(self):
        from unittest.mock import MagicMock

        cfg = MagicMock()
        cfg.get.side_effect = lambda k, d=None: d
        return cfg

    def test_llm_models_endpoint_uses_query_base_url(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """#328-AC: name matches issue-body anchor."""
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)

        captured: dict = {}

        class _FakeAdapter:
            def list_models(self):
                return [{"id": "remote-model-1", "model": "remote-model-1"}]

        def _fake_build_inner(provider, config, secrets, **kwargs):
            captured["provider"] = provider
            captured["base_url_override"] = kwargs.get("base_url_override")
            return _FakeAdapter()

        # server.py uses `from samuel.adapters.llm.factory import _build_inner`
        # lazily inside the GET handler — patching the module-level symbol
        # works because the import happens at request time.
        import samuel.adapters.llm.factory as _factory

        monkeypatch.setattr(_factory, "_build_inner", _fake_build_inner)

        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(
            bus, host="127.0.0.1", port=0, config=self._make_config(), authentication=False
        )
        with _serve(srv):
            from urllib.parse import quote

            url = _url(
                srv,
                "/api/v1/dashboard/llm/models?provider=lmstudio&base_url="
                + quote("http://192.0.2.21:1234"),
            )
            resp = urllib.request.urlopen(url, timeout=2)
            import json as _json

            body = _json.loads(resp.read())
            assert body["provider"] == "lmstudio"
            assert body["models"] == [{"id": "remote-model-1", "model": "remote-model-1"}]
            # Backend must have forwarded the base_url to _build_inner
            assert captured["base_url_override"] == "http://192.0.2.21:1234"

    def test_llm_models_endpoint_without_base_url_uses_config_default(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If base_url query is omitted, the override is None — adapter falls back to config."""
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)

        captured: dict = {}

        class _FakeAdapter:
            def list_models(self):
                return []

        def _fake_build_inner(provider, config, secrets, **kwargs):
            captured["base_url_override"] = kwargs.get("base_url_override")
            return _FakeAdapter()

        import samuel.adapters.llm.factory as _factory

        monkeypatch.setattr(_factory, "_build_inner", _fake_build_inner)

        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(
            bus, host="127.0.0.1", port=0, config=self._make_config(), authentication=False
        )
        with _serve(srv):
            url = _url(srv, "/api/v1/dashboard/llm/models?provider=ollama")
            resp = urllib.request.urlopen(url, timeout=2)
            assert resp.status == 200
            assert captured["base_url_override"] is None

    def test_model_choices_include_task_specific_reasoning_and_suitability(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        from samuel.adapters.llm import costs

        monkeypatch.setattr(
            costs,
            "get_models_for_provider",
            lambda provider: [{"id": "vendor/reasoner", "model": "vendor/reasoner"}],
        )
        monkeypatch.setattr(
            costs,
            "get_model_reasoning_info",
            lambda model: {
                "is_reasoning": True,
                "source": "openrouter_metadata",
                "metadata": {"supported_efforts": ["high"]},
            },
        )
        seen: dict = {}

        def _suitability(model, task, *, threshold=50.0, overqualification_margin_ratio=None):
            seen.update(
                model=model,
                task=task,
                threshold=threshold,
                margin=overqualification_margin_ratio,
            )
            return {
                "available": True,
                "status": "below_threshold",
                "index": "coding_index",
                "score": 41.0,
                "threshold": threshold,
            }

        monkeypatch.setattr(costs, "get_model_suitability", _suitability)
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(
            bus, host="127.0.0.1", port=0, config=self._make_config(), authentication=False
        )
        with _serve(srv):
            response = urllib.request.urlopen(
                _url(
                    srv,
                    "/api/v1/dashboard/llm/models?provider=openrouter"
                    "&task=implementation&threshold=55",
                ),
                timeout=2,
            )
            body = json.loads(response.read())

        assert seen == {
            "model": "vendor/reasoner",
            "task": "implementation",
            "threshold": 55.0,
            "margin": 0.2,
        }
        assert body["models"][0]["reasoning_info"]["is_reasoning"] is True
        assert body["models"][0]["suitability"]["status"] == "below_threshold"
        assert body["models"][0]["cost_advisory"]["recommendation"] is None

    @pytest.mark.parametrize(
        "query",
        (
            "provider=openrouter&task=planning&margin=1.1",
            "provider=openrouter&task=planning&cost_advisory=maybe",
        ),
    )
    def test_model_choices_reject_invalid_advisory_controls(
        self, monkeypatch: pytest.MonkeyPatch, query: str
    ) -> None:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(
            bus, host="127.0.0.1", port=0, config=self._make_config(), authentication=False
        )
        with _serve(srv), pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(
                _url(
                    srv,
                    "/api/v1/dashboard/llm/models?" + query,
                ),
                timeout=2,
            )

        assert exc.value.code == 400

    def test_model_refresh_endpoint_calls_real_cache_refresh(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "benchmark-key")
        from samuel.adapters.llm import costs

        seen: dict = {}

        def _refresh(*, api_key=None, config=None):
            seen["api_key"] = api_key
            seen["config"] = config
            return {
                "count": 420,
                "benchmark_count": 125,
                "benchmark_error": None,
                "fetched_at": 1,
                "error": None,
            }

        monkeypatch.setattr(costs, "refresh_pricing", _refresh)
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(
            bus, host="127.0.0.1", port=0, config=self._make_config(), authentication=False
        )
        with _serve(srv):
            request = urllib.request.Request(
                _url(srv, "/api/v1/dashboard/llm/models/refresh"),
                data=b"{}",
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            response = urllib.request.urlopen(request, timeout=2)
            body = json.loads(response.read())

        assert response.status == 200
        assert seen["api_key"] == "benchmark-key"
        assert seen["config"] is srv.RequestHandlerClass.dashboard._config
        assert body["count"] == 420
        assert body["benchmark_count"] == 125


class TestSetupLabelsRoute:
    def test_setup_labels_route_reachable(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)

        class _FakeSCM:
            def list_labels(self):
                return []

            def create_label(self, name, color, description=""):
                return {"id": 1, "name": name, "color": color, "description": description}

        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})

        # Stage labels.json inside tmp_path/config, and chdir into tmp_path so
        # SetupHandler (project_root=.) picks it up.
        (tmp_path / "config").mkdir()
        import json as _json

        (tmp_path / "config" / "labels.json").write_text(
            _json.dumps({"labels": [{"name": "ready-for-agent", "color": "0e8a16"}]})
        )
        monkeypatch.chdir(tmp_path)

        srv = create_server(
            bus,
            host="127.0.0.1",
            port=0,
            scm=_FakeSCM(),
            configuration_mode="setup",
            authentication=False,
        )
        with _serve(srv):
            req = urllib.request.Request(
                _url(srv, "/api/v1/setup/labels"),
                data=b"",
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=2)
            body = _json.loads(resp.read())
            assert body.get("synced") is True
            assert "ready-for-agent" in body.get("created", [])


# #359: Click-Expand fuer OWASP/AI-Act-Codes im Audit-Trail + Schranken-Protokoll
class TestClickExpandMarkers:
    def test_audit_trail_has_click_expand_markers(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """HTML enthaelt die Klassen + data-attributes fuer das
        Click-Expand-Pattern im Workflow-Issue-Detail Audit-Trail."""
        import samuel.server as _srv

        html = _srv.DASHBOARD_HTML
        # Audit-Trail-Renderer
        assert "trail-info-cell" in html
        assert "trail-info-row" in html
        assert "data-trail-idx" in html
        assert "data-trail-info-for" in html
        # ⓘ-Symbol als visueller Hint (HTML-Entity)
        assert "&#9432;" in html

    def test_security_barrier_has_click_expand_markers(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """HTML enthaelt die Klassen + data-attributes fuer das
        Click-Expand-Pattern im Security-Tab Schranken-Protokoll."""
        import samuel.server as _srv

        html = _srv.DASHBOARD_HTML
        assert "barrier-info-cell" in html
        assert "barrier-info-row" in html
        assert "data-barrier-idx" in html
        assert "data-barrier-info-for" in html

    def test_compliance_legend_helpers_defined(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """JS-Helpers fuer den lazy Legend-Lookup sind im HTML."""
        import samuel.server as _srv

        html = _srv.DASHBOARD_HTML
        assert "ensureLegend" in html
        assert "owaspDesc" in html
        assert "aiActDesc" in html
        assert "complianceCache" in html

    def test_compliance_legend_endpoint_serves_owasp_and_ai_act(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """End-to-end: Endpoint liefert die Daten die das JS erwartet —
        mind. ein OWASP- und ein AI-Act-Eintrag mit Beschreibung."""
        import json as _json

        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0, authentication=False)
        with _serve(srv):
            resp = urllib.request.urlopen(
                _url(srv, "/api/v1/dashboard/compliance/legend"),
                timeout=2,
            )
            body = _json.loads(resp.read())
        # Legende kommt direkt aus core.owasp / core.ai_act — Spotcheck.
        owasp = body.get("owasp") or []
        ai_act = body.get("ai_act") or []
        assert owasp, "owasp legend must not be empty"
        assert ai_act, "ai_act legend must not be empty"
        # Mindestens ein OWASP-Eintrag mit Description
        assert any(r.get("description") for r in owasp), "owasp entries need descriptions"
        assert any(r.get("description") or r.get("title") for r in ai_act), (
            "ai_act entries need descriptions"
        )


class TestAcceptanceCheckRendering:
    def test_workflow_detail_renders_manual_pending_separately(self) -> None:
        """#514: Der vorhandene acceptance_checks-Slot ist im UI sichtbar.

        MANUAL wird dabei weder als PASS noch als FAIL dargestellt.
        """
        import samuel.server as _srv

        html = _srv.DASHBOARD_HTML
        assert 'id="wd-acceptance-checks"' in html
        assert "d.acceptance_checks" in html
        assert "MANUAL PENDING" in html
        assert "state==='manual_pending'" in html


class TestWorkflowStageRendering:
    def test_gate_result_table_distinguishes_skip_from_failure(self) -> None:
        import samuel.server as _srv

        html = _srv.DASHBOARD_HTML
        assert 'id="wd-gate-results"' in html
        assert "d.gate_results" in html
        assert "skipped_precondition:'SKIP'" in html
        assert "not_applicable:'N/A'" in html

    def test_blocked_and_not_attempted_stages_are_distinct_from_failure(self) -> None:
        """#578: the browser preserves the outcome-bound API taxonomy."""

        import samuel.server as _srv

        html = _srv.DASHBOARD_HTML
        assert "st.status==='blocked'?'#b45309'" in html
        assert "esc(st.status)" in html

    def test_workflow_detail_http_preserves_bound_stage_outcomes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        from unittest.mock import MagicMock

        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        correlation_id = "run-578-http"
        rows: list[tuple[str, dict[str, object]]] = [
            ("GateEvaluationCompleted", {"blocked": True}),
            (
                "HealingClassified",
                {"classification": "not_healable", "reason": "ambiguous_failed_criteria"},
            ),
            ("WorkflowBlocked", {"reason": "bound_healing:ambiguous_failed_criteria"}),
            ("CreatePR", {}),
        ]
        (log_dir / "agent.jsonl").write_text(
            "".join(
                json.dumps(
                    {
                        "ts": f"t{index}",
                        "name": "AuditEvent",
                        "payload": {
                            "message_name": name,
                            "issue": 578,
                            "correlation_id": correlation_id,
                            **payload,
                        },
                    }
                )
                + "\n"
                for index, (name, payload) in enumerate(rows, start=1)
            ),
            encoding="utf-8",
        )
        config = MagicMock()
        config.get.side_effect = lambda key, default=None: (
            str(tmp_path) if key == "agent.data_dir" else default
        )
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0, config=config, authentication=False)

        with _serve(srv):
            response = urllib.request.urlopen(
                _url(srv, "/api/v1/dashboard/workflow/578"),
                timeout=2,
            )
            body = json.loads(response.read())

        assert response.status == 200
        assert body["stages"]["gates"]["status"] == "failed"
        assert body["stages"]["pr"]["status"] == "blocked"
        assert body["stages"]["healing"]["status"] == "not_attempted"
        assert body["stages"]["healing"]["count"] == 0


class TestPassiveScoreRendering:
    def test_bound_observation_is_never_rendered_as_pass_or_fail(self) -> None:
        import samuel.server as _srv

        html = _srv.DASHBOARD_HTML
        assert "Qualitätsbeobachtung" in html
        assert "h.non_binding===true" in html
        assert "NICHT BINDEND" in html
        assert "LEGACY PASS" in html
        assert "LEGACY FAIL" in html


class TestQualitySeriesRendering:
    def test_quality_tables_name_series_and_attribution_buckets(self) -> None:
        import samuel.server as _srv

        html = _srv.DASHBOARD_HTML
        assert "Aktive Score-Serie" in html
        assert "Serien-Calls" in html
        assert "Unattrib." in html
        assert "Andere Serien" in html
        assert "qualitySeriesLabel" in html
        assert "unattributed_calls" in html
        assert "other_series_calls" in html
        assert "keine Legacy-/Policy-/Formelmischung" in html


class TestDashboardJavaScript:
    def test_operator_dashboard_keeps_all_declared_feature_tabs(self) -> None:
        """A dashboard edit must not silently drop an existing feature surface."""

        expected_tabs = {
            "status",
            "llm",
            "quality",
            "activity",
            "workflow",
            "problems",
            "logs",
            "security",
            "compliance",
            "setup",
            "settings",
            "selfcheck",
        }
        collector = _DashboardSurfaceCollector()
        collector.feed(DASHBOARD_HTML)

        assert collector.navigation_tabs == expected_tabs
        assert collector.content_tabs == expected_tabs

    def test_every_inline_script_parses_as_javascript(self) -> None:
        import tree_sitter_javascript
        from tree_sitter import Language, Parser

        collector = _InlineScriptCollector()
        collector.feed(DASHBOARD_HTML)
        parser = Parser(Language(tree_sitter_javascript.language()))

        assert collector.scripts, "dashboard must contain inline JavaScript"
        for number, script in enumerate(collector.scripts, start=1):
            tree = parser.parse(script.encode("utf-8"))
            assert not tree.root_node.has_error, f"inline script {number} is invalid JavaScript"

    def test_linebreak_guard_distinguishes_javascript_lexical_contexts(self) -> None:
        valid_script = """// ' and \" are harmless in comments
/* so are ' and \" in block comments */
const template = `line one
' and \" remain template content`;
const continued = 'line one\\
line two';
"""
        invalid_script = "const broken = 'line one\nline two';"

        assert _unescaped_string_linebreak(valid_script) is None
        assert _unescaped_string_linebreak(invalid_script) is not None

    def test_problem_steps_use_an_escaped_javascript_linebreak(self) -> None:
        """#539: Python must not consume the JavaScript newline escape."""
        import samuel.server as _srv

        assert "map(s=>'• '+s).join('\\n')" in _srv.DASHBOARD_HTML

    def test_inline_scripts_have_no_raw_linebreaks_in_normal_strings(self) -> None:
        """#539: validate the complete JavaScript delivered to the browser."""
        import samuel.server as _srv

        collector = _InlineScriptCollector()
        collector.feed(_srv.DASHBOARD_HTML)
        assert collector.scripts, "dashboard must contain inline JavaScript"
        for number, script in enumerate(collector.scripts, start=1):
            finding = _unescaped_string_linebreak(script)
            assert finding is None, (
                f"inline script {number} has an unescaped line break in a normal "
                f"JavaScript string at line {finding[0]}, column {finding[1]}"
            )


class TestTransferWarningsRoute:
    def test_route_uses_same_provider_catalogue_as_config(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """#486: The dashboard must expose every configured provider.

        A provider without a privacy location must remain visible and fail
        closed as an unknown third-country transfer.
        """
        from unittest.mock import MagicMock

        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        (tmp_path / "llm").mkdir()
        (tmp_path / "llm" / "providers.json").write_text(
            json.dumps(
                {
                    "providers": {
                        "claude": {"model": "claude-sonnet-4-6"},
                        "new-provider": {"model": "example-model"},
                    }
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / "privacy.json").write_text(
            json.dumps(
                {
                    "allowed_regions": ["EU", "EEA", "CH"],
                    "provider_locations": {"claude": "US"},
                }
            ),
            encoding="utf-8",
        )
        cfg = MagicMock()
        cfg.get.side_effect = lambda key, default=None: (
            str(tmp_path) if key == "agent.config_dir" else default
        )

        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0, config=cfg, authentication=False)
        with _serve(srv):
            response = urllib.request.urlopen(
                _url(srv, "/api/v1/dashboard/transfer_warnings"),
                timeout=2,
            )
            warnings = json.loads(response.read())["transfer_warnings"]

        by_provider = {entry["provider"]: entry for entry in warnings}
        assert set(by_provider) == {"claude", "new-provider"}
        assert by_provider["claude"]["location"] == "US"
        assert by_provider["new-provider"]["location"] == "unknown"
        assert by_provider["new-provider"]["allowed"] is False
        assert by_provider["new-provider"]["warning"]

    def test_disabled_flag_suppresses_warnings_in_route_and_status(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        from unittest.mock import MagicMock

        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        (tmp_path / "llm").mkdir()
        (tmp_path / "llm" / "providers.json").write_text(
            json.dumps({"providers": {"openai": {"model": "gpt-4o-mini"}}}),
            encoding="utf-8",
        )
        (tmp_path / "privacy.json").write_text(
            json.dumps(
                {
                    "allowed_regions": ["EU", "EEA", "CH"],
                    "provider_locations": {"openai": "US"},
                    "transfer_warning": False,
                }
            ),
            encoding="utf-8",
        )
        cfg = MagicMock()
        cfg.get.side_effect = lambda key, default=None: (
            str(tmp_path) if key in {"agent.config_dir", "agent.data_dir"} else default
        )

        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0, config=cfg, authentication=False)
        with _serve(srv):
            response = urllib.request.urlopen(
                _url(srv, "/api/v1/dashboard/transfer_warnings"),
                timeout=2,
            )
            entries = json.loads(response.read())["transfer_warnings"]
            status_response = urllib.request.urlopen(
                _url(srv, "/api/v1/dashboard/status"),
                timeout=2,
            )
            status = json.loads(status_response.read())

        assert entries == [
            {
                "provider": "openai",
                "location": "US",
                "allowed": False,
                "warning": None,
            }
        ]
        assert status["transfer_warnings"] == []


# #364/#477: delete_prompt keeps idempotent semantics and remains protected by
# the dashboard API key after removal of the entitlement gate.
class TestPromptDeleteIdempotent:
    def _make_config_pointing_to(self, tmp_path):
        from unittest.mock import MagicMock

        cfg = MagicMock()
        cfg.get.side_effect = lambda k, d=None: str(tmp_path) if k == "agent.config_dir" else d
        return cfg

    def test_delete_prompt_returns_200_when_no_override_exists(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """#364-AC: idempotenter No-op kommt als HTTP 200 zurueck mit
        ``deleted=False`` + ``reason="no override at this scope"``."""
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)

        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(
            bus,
            host="127.0.0.1",
            port=0,
            config=self._make_config_pointing_to(tmp_path),
            configuration_mode="setup",
            authentication=False,
        )
        with _serve(srv):
            import json as _json

            req = urllib.request.Request(
                _url(srv, "/api/v1/dashboard/llm/prompts/nonexistent.md"),
                method="DELETE",
            )
            resp = urllib.request.urlopen(req, timeout=2)
            assert resp.status == 200
            body = _json.loads(resp.read())
            assert body.get("deleted") is False
            assert "no override" in body.get("reason", "")
            assert body.get("error") is None

    def test_delete_prompt_is_frozen_in_production(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        prompt = tmp_path / "llm" / "prompts" / "planner.md"
        prompt.parent.mkdir(parents=True)
        prompt.write_text("operator override", encoding="utf-8")
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(
            bus,
            host="127.0.0.1",
            port=0,
            config=self._make_config_pointing_to(tmp_path),
            authentication=False,
        )

        with _serve(srv):
            req = urllib.request.Request(
                _url(srv, "/api/v1/dashboard/llm/prompts/planner.md"),
                method="DELETE",
            )
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req, timeout=2)
            body = json.loads(exc_info.value.read())

        assert exc_info.value.code == 409
        assert body["code"] == "configuration_frozen"
        assert prompt.read_text(encoding="utf-8") == "operator override"

    def test_delete_prompt_requires_dashboard_api_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """#477: removing entitlements must not remove HTTP authorization."""
        monkeypatch.setenv("SAMUEL_API_KEY", "dashboard-secret")
        (tmp_path / "auth.json").write_text(
            (Path(__file__).parents[1] / "config" / "auth.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        prompt = tmp_path / "llm" / "prompts" / "planner.md"
        prompt.parent.mkdir(parents=True)
        prompt.write_text("protected", encoding="utf-8")

        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(
            bus,
            host="127.0.0.1",
            port=0,
            config=self._make_config_pointing_to(tmp_path),
        )
        with _serve(srv):
            import json as _json

            req = urllib.request.Request(
                _url(srv, "/api/v1/dashboard/llm/prompts/planner.md"),
                method="DELETE",
            )
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req, timeout=2)
            assert exc_info.value.code == 401
            body = _json.loads(exc_info.value.read())
            assert "unauthorized" in body.get("error", "")
        assert prompt.read_text(encoding="utf-8") == "protected"


def test_native_diagnostic_occurrences_survive_passive_problem_http(tmp_path):
    import logging
    from unittest.mock import MagicMock

    from samuel.adapters.audit.jsonl import JSONLAuditSink
    from samuel.core.bus import AuditMiddleware
    from samuel.core.issue_context import issue_scope
    from samuel.core.logging import AuditDiagnosticHandler

    config = MagicMock()
    config.get.side_effect = lambda key, default=None: (
        str(tmp_path) if key == "agent.data_dir" else default
    )
    bus = Bus()
    bus.add_middleware(
        AuditMiddleware(JSONLAuditSink(tmp_path / "logs" / "agent.jsonl", rotation="none"))
    )
    mirror = AuditDiagnosticHandler(bus)
    logger = logging.getLogger("samuel.core.bootstrap")
    for index in range(30):
        record = logger.makeRecord(
            logger.name,
            logging.ERROR,
            "samuel/core/bootstrap.py",
            615,
            "Runtime run-projection backfill failed",
            (),
            (KeyError, KeyError("private missing key"), None),
        )
        with issue_scope(890, f"diagnostic-{index}"):
            mirror.emit(record)
    events: list[Event] = []
    bus.subscribe("*", events.append)
    srv = create_server(bus, host="127.0.0.1", port=0, config=config, authentication=False)
    with (
        _serve(srv),
        urllib.request.urlopen(_url(srv, "/api/v1/dashboard/problems"), timeout=2) as response,
    ):
        payload = json.loads(response.read())
    data = payload.get("data", payload)
    row = data["problems"][0]
    assert row["count"] == 30
    assert row["reason"] == "Runtime run-projection backfill failed"
    assert row["exception"] == "KeyError"
    assert row["logger"] == "samuel.core.bootstrap"
    assert len(row["instances"]) == 20
    assert {i["correlation_id"] for i in row["instances"]} == {
        f"diagnostic-{i}" for i in range(10, 30)
    }
    assert "private missing key" not in json.dumps(data)
    assert events == []


def test_problem_view_renders_observed_detail_without_inventing_causality():
    import shutil
    import subprocess

    import tree_sitter_javascript
    from tree_sitter import Language, Parser

    node = shutil.which("node")
    if not node:
        pytest.skip(
            "Node is needed only for executing the UI regression; HTTP and JS syntax checks remain mandatory"
        )
    collector = _InlineScriptCollector()
    collector.feed(DASHBOARD_HTML)
    parser = Parser(Language(tree_sitter_javascript.language()))
    functions = []
    for script in collector.scripts:
        for statement in parser.parse(script.encode()).root_node.named_children:
            name = statement.child_by_field_name("name")
            source = statement.text or b""
            if (
                statement.type == "function_declaration"
                and name
                and name.text in (b"filterProblems", b"fmtTime")
                or statement.type == "lexical_declaration"
                and source.startswith(b"const esc=")
            ):
                functions.append(source.decode())
    assert len(functions) == 3
    harness = (
        """
const elements = new Map();
const document = {
 getElementById(id) {if (!elements.has(id)) elements.set(id, {value:'',checked:false,innerHTML:''});return elements.get(id);},
 querySelectorAll() {return [];},
 createElement() {return {textContent:'',get innerHTML(){return String(this.textContent).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}};}
};
const allProblems = JSON.parse(require('fs').readFileSync(0, 'utf8'));
"""
        + "\n".join(functions)
        + "\nfilterProblems();process.stdout.write(document.getElementById('prob-body').innerHTML);"
    )
    row = {
        "title": "DiagnosticRaised",
        "reason": "operation failed <script>",
        "exception": "KeyError",
        "status": "active",
        "category": "system",
        "level": "error",
        "count": 30,
        "logger": "bootstrap",
        "cause": "Root Cause nicht belegt",
        "instances": [
            {
                "timestamp": "now",
                "issue": 890,
                "correlation_id": f"run-{i}",
                "reason": "operation failed <script>",
            }
            for i in range(30)
        ],
    }
    result = subprocess.run(
        [node, "-e", harness],
        input=json.dumps([row]),
        text=True,
        capture_output=True,
        check=True,
        timeout=5,
    )
    html = result.stdout
    assert "Diagnose: operation failed &lt;script&gt;" in html
    assert "Klasse: KeyError" in html
    assert "Root Cause nicht belegt" in html
    assert "Korrelation belegt keine Kausalität" in html
    assert "Korrelation run-10" in html and "Korrelation run-29" in html
    assert "Korrelation run-9 ·" not in html
    assert "<script>" not in html


@pytest.mark.parametrize("writable", [False, True])
def test_setup_view_explains_existing_reconfiguration_lifecycle(writable):
    import shutil
    import subprocess

    import tree_sitter_javascript
    from tree_sitter import Language, Parser

    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the UI behavior regression")
    collector = _InlineScriptCollector()
    collector.feed(DASHBOARD_HTML)
    parser = Parser(Language(tree_sitter_javascript.language()))
    functions = []
    for script in collector.scripts:
        for statement in parser.parse(script.encode()).root_node.named_children:
            name = statement.child_by_field_name("name")
            if (
                statement.type == "function_declaration"
                and name
                and name.text == b"loadSetupWizard"
            ):
                functions.append((statement.text or b"").decode())
    assert len(functions) == 1
    harness = (
        """
const payload = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const elements = new Map();
const document = {getElementById(id){
 if(!elements.has(id))elements.set(id,{textContent:'',value:'',disabled:false});
 return elements.get(id);
}};
let setupLoaded=false,setupWritable=false;
const loadSetupModels=()=>{};
const apiFetch=async (path,options)=>{
 if(path!=='/api/v1/setup/status'||options)throw new Error('Unexpected product effect');
 return {ok:true,status:200,json:async()=>payload};
};
"""
        + functions[0]
        + """
loadSetupWizard().then(()=>process.stdout.write(JSON.stringify({
 text:document.getElementById('setup-status').textContent,
 disabled:document.getElementById('setup-save').disabled,
 fieldsDisabled:document.getElementById('setup-fields').disabled
}))).catch(()=>process.exit(1));
"""
    )
    result = subprocess.run(
        [node, "-e", harness],
        input=json.dumps(
            {"first_run": False, "configuration": {"writable": writable}, "values": {}}
        ),
        text=True,
        capture_output=True,
        check=True,
        timeout=5,
    )
    view = json.loads(result.stdout)
    assert view["disabled"] is (not writable)
    assert view["fieldsDisabled"] is (not writable)
    text = view["text"]
    if writable:
        assert "Schreibmodus aktiv" in text and "Neustart" in text
    else:
        steps = [
            "Produktionsdienst stoppen",
            "derselben Konfiguration",
            "--configuration-mode setup",
            "Setup beenden",
            "Produktionsruntime neu erzeugen",
            "gespeicherte/wirksame Werte",
        ]
        positions = [text.index(step) for step in steps]
        assert positions == sorted(positions)


@pytest.mark.parametrize("status", [200, 401, 403, 500])
def test_setup_fields_fail_closed_until_writable_status(status):
    import shutil
    import subprocess

    import tree_sitter_javascript
    from tree_sitter import Language, Parser

    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the UI behavior regression")
    collector = _InlineScriptCollector()
    collector.feed(DASHBOARD_HTML)
    parser = Parser(Language(tree_sitter_javascript.language()))
    functions = []
    for script in collector.scripts:
        for statement in parser.parse(script.encode()).root_node.named_children:
            name = statement.child_by_field_name("name")
            if (
                statement.type == "function_declaration"
                and name
                and name.text == b"loadSetupWizard"
            ):
                functions.append((statement.text or b"").decode())
    assert len(functions) == 1
    harness = (
        """
const status=JSON.parse(require('fs').readFileSync(0,'utf8'));
const elements=new Map();
const document={getElementById(id){
 if(!elements.has(id))elements.set(id,{textContent:'',value:'operator edit',disabled:false});
 return elements.get(id);
}};
let setupLoaded=true,setupWritable=true;
const apiFetch=async()=>({ok:status===200,status,json:async()=>({configuration:{},values:{}})});
"""
        + functions[0]
        + """
loadSetupWizard().then(()=>process.stdout.write(JSON.stringify({
 writable:setupWritable,fields:document.getElementById('setup-fields').disabled,
 save:document.getElementById('setup-save').disabled,
 value:document.getElementById('setup-scm-token').value
}))).catch(()=>process.exit(1));
"""
    )
    observed = json.loads(
        subprocess.run(
            [node, "-e", harness],
            input=json.dumps(status),
            text=True,
            capture_output=True,
            check=True,
            timeout=5,
        ).stdout
    )
    assert observed == {"writable": False, "fields": True, "save": True, "value": "operator edit"}


@pytest.mark.parametrize("status", [400, 401, 403, 409])
def test_setup_save_surfaces_backend_error_and_preserves_authority(status):
    import shutil
    import subprocess

    import tree_sitter_javascript
    from tree_sitter import Language, Parser

    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the UI behavior regression")
    collector = _InlineScriptCollector()
    collector.feed(DASHBOARD_HTML)
    parser = Parser(Language(tree_sitter_javascript.language()))
    functions = []
    for script in collector.scripts:
        for statement in parser.parse(script.encode()).root_node.named_children:
            name = statement.child_by_field_name("name")
            if (
                statement.type == "function_declaration"
                and name
                and name.text in {b"setupValue", b"saveSetupWizard"}
            ):
                functions.append((statement.text or b"").decode())
    assert len(functions) == 2
    harness = (
        """
const status=JSON.parse(require('fs').readFileSync(0,'utf8'));
const elements=new Map(),effects=[];
const document={getElementById(id){
 if(!elements.has(id))elements.set(id,{value:'retained input',disabled:false,style:{},
 focus(options){effects.push(['focus',id,options]);},
 scrollIntoView(options){effects.push(['scroll',id,options]);}});
 return elements.get(id);
}};
let setupWritable=true;
const showToast=()=>{};
const apiFetch=async(path,options)=>{
 if(!document.getElementById('setup-fields').disabled)throw Error('inputs enabled during save');
 if(path!=='/api/v1/setup/configure'||options.method!=='POST')throw Error('unexpected request');
 return {ok:false,status,json:async()=>status===400?
  {errors:['SCM_REQUIRED_STATUS_CONTEXT must not be empty']}:
  {code:status===409?'configuration_frozen':'access_denied',error:'access denied'}};
};
"""
        + "\n".join(functions)
        + """
saveSetupWizard().then(()=>process.stdout.write(JSON.stringify({
 text:document.getElementById('setup-result').textContent,effects,
 fields:document.getElementById('setup-fields').disabled,
 save:document.getElementById('setup-save').disabled,
 token:document.getElementById('setup-scm-token').value
}))).catch(()=>process.exit(1));
"""
    )
    observed = json.loads(
        subprocess.run(
            [node, "-e", harness],
            input=json.dumps(status),
            text=True,
            capture_output=True,
            check=True,
            timeout=5,
        ).stdout
    )
    assert observed["fields"] is (status != 400)
    assert observed["save"] is (status != 400)
    assert observed["token"] == "retained input"
    assert observed["effects"] == [
        ["focus", "setup-result", {"preventScroll": True}],
        ["scroll", "setup-result", {"block": "nearest"}],
    ]
    if status == 400:
        assert "SCM_REQUIRED_STATUS_CONTEXT must not be empty" in observed["text"]
        assert "korrigieren" in observed["text"]


def test_setup_markup_disables_inputs_before_status_and_explains_existing_test_policy():
    class SetupMarkup(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_fields = False
            self.controls = []
            self.fieldset = {}
            self.result = {}

        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            if tag == "fieldset" and attributes.get("id") == "setup-fields":
                self.in_fields = True
                self.fieldset = attributes
            if self.in_fields and tag in {"input", "select", "button"}:
                self.controls.append(attributes.get("id"))
            if attributes.get("id") == "setup-result":
                self.result = attributes

        def handle_endtag(self, tag):
            if tag == "fieldset":
                self.in_fields = False

    markup = SetupMarkup()
    markup.feed(DASHBOARD_HTML)
    assert "disabled" in markup.fieldset
    assert {"setup-scm-token", "setup-llm-api-key", "setup-dashboard-api-key", "setup-save"} <= set(
        markup.controls
    )
    assert markup.result["tabindex"] == "-1"
    assert markup.result["aria-live"] == "polite"
    assert "config/eval.json" in DASHBOARD_HTML and "samuel-container toolchain" in DASHBOARD_HTML
    assert "Doctor-PASS ersetzt keinen Candidate-Test-PASS" in DASHBOARD_HTML


@pytest.mark.parametrize("mode, status", [("setup", 400), ("production", 409)])
def test_setup_http_required_check_error_and_freeze_precede_probes_and_writes(
    tmp_path, monkeypatch, mode, status
):
    from samuel.core.config import FileConfig

    for key in (
        "SAMUEL_API_KEY",
        "SCM_REQUIRED_STATUS_CONTEXT",
        "SCM_TOKEN",
        "SCM_URL",
        "SCM_REPO",
    ):
        monkeypatch.delenv(key, raising=False)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "agent.json").write_text(json.dumps({"config_dir": str(config_dir)}))
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    probes = []

    def probe(*args):
        probes.append(args)
        raise AssertionError("Validation/freeze must run before live probes")

    bus = Bus()
    srv = create_server(
        bus,
        host="127.0.0.1",
        port=0,
        config=FileConfig(config_dir),
        setup_scm_tester=probe,
        setup_llm_tester=probe,
        configuration_mode=mode,
        authentication=False,
    )
    with _serve(srv):
        request = urllib.request.Request(
            _url(srv, "/api/v1/setup/configure"),
            data=json.dumps(
                {
                    "scm_provider": "gitea",
                    "scm_url": "https://example.test",
                    "scm_repo": "owner/repo",
                    "scm_token": "synthetic-secret",
                    "scm_required_status_context": "",
                    "llm_provider": "manual",
                }
            ).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=2)
        raw = error.value.read()
        body = json.loads(raw)
    assert error.value.code == status
    if mode == "setup":
        assert any("SCM_REQUIRED_STATUS_CONTEXT" in entry for entry in body["errors"])
    else:
        assert body["code"] == "configuration_frozen"
    assert b"synthetic-secret" not in raw
    assert probes == []
    assert {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize(
    "scope, subdir, expected_source",
    [
        ("generic", "", "operator-generic"),
        ("provider:deepseek", "provider/deepseek", "operator-provider:deepseek"),
        ("model:test-model", "model/test-model", "operator-model:test-model"),
    ],
)
@pytest.mark.parametrize("readable", [True, False])
def test_scoped_prompt_http_source_matches_exact_content(
    tmp_path, monkeypatch, scope, subdir, expected_source, readable
):
    from unittest.mock import MagicMock

    monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
    root = tmp_path / "llm" / "prompts"
    root.mkdir(parents=True)
    (root / "planner.md").write_text("GENERIC", encoding="utf-8")
    selected = root / subdir / "planner.md"
    selected.parent.mkdir(parents=True, exist_ok=True)
    if readable:
        selected.write_text("SELECTED", encoding="utf-8")
    else:
        selected.write_bytes(b"\xff")
    config = MagicMock()
    config.get.side_effect = lambda key, default=None: (
        str(tmp_path) if key == "agent.config_dir" else default
    )
    bus = Bus()
    bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
    srv = create_server(bus, host="127.0.0.1", port=0, config=config, authentication=False)
    with _serve(srv):
        response = urllib.request.urlopen(
            _url(srv, "/api/v1/dashboard/llm/prompts/planner.md?scope=" + scope),
            timeout=2,
        )
        body = json.loads(response.read())
    assert body["scope"] == scope
    assert body["content"] == ("SELECTED" if readable else "")
    if readable:
        assert body["source"]["source"] == expected_source
        assert body["source"]["path"] == str(selected)
    else:
        assert body["source"] == {"source": "none", "path": "", "mtime": 0.0}


@pytest.mark.parametrize(
    ("zone", "expected_zone"),
    [
        ("Europe/Berlin", "Europe/Berlin"),
        ("America/New_York", "America/New_York"),
        ("UTC", "UTC"),
        ("Invalid/Zone", "UTC"),
    ],
)
def test_dashboard_binds_existing_setup_timezone_without_workflow_effects(
    tmp_path, zone, expected_zone
):
    from samuel.cli import _write_agent_timezone
    from samuel.core.config import FileConfig

    _write_agent_timezone(tmp_path, zone)
    bus = Bus()
    bus.config = FileConfig(tmp_path)
    events: list[Event] = []
    bus.subscribe("*", events.append)
    srv = create_server(bus, host="127.0.0.1", port=0, config=bus.config, authentication=False)
    with _serve(srv):
        with urllib.request.urlopen(_url(srv, "/dashboard"), timeout=2) as response:
            html = response.read().decode()
        with urllib.request.urlopen(_url(srv, "/api/v1/dashboard/status"), timeout=2) as response:
            status = json.loads(response.read())
    assert f'data-timezone="{expected_zone}"' in html
    assert status["timezone"] == expected_zone
    assert events == []


@pytest.mark.parametrize(
    ("zone", "value", "expected"),
    [
        (
            "Europe/Berlin",
            "2026-10-04T07:49:40.754394+00:00",
            ["09:49:40", "GMT+2", "Europe/Berlin"],
        ),
        ("Europe/Berlin", "2026-01-04T07:49:40Z", ["08:49:40", "GMT+1", "Europe/Berlin"]),
        ("Europe/Berlin", "2026-10-25T00:30:00Z", ["02:30:00", "GMT+2"]),
        ("Europe/Berlin", "2026-10-25T01:30:00Z", ["02:30:00", "GMT+1"]),
        ("Europe/Berlin", "2026-10-04T09:49:40+02:00", ["09:49:40", "GMT+2"]),
        ("Europe/Berlin", "2026-10-04 07:49:40.754394+00:00", ["09:49:40", "GMT+2"]),
        ("UTC", "2026-10-04T07:49:40Z", ["07:49:40", "UTC"]),
        ("Invalid/Zone", "2026-10-04T07:49:40Z", ["07:49:40", "UTC", "nicht verfügbar"]),
        ("Europe/Berlin", "2026-10-04T07:49:40", ["2026-10-04T07:49:40", "Zeitzone unbekannt"]),
        ("Europe/Berlin", "invalid<script>", ["invalid<script>"]),
        ("Europe/Berlin", "", ["-"]),
    ],
)
def test_dashboard_time_format_uses_explicit_offset_not_browser_timezone(zone, value, expected):
    import os
    import shutil
    import subprocess

    import tree_sitter_javascript
    from tree_sitter import Language, Parser

    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the UI behavior regression")
    collector = _InlineScriptCollector()
    collector.feed(DASHBOARD_HTML)
    parser = Parser(Language(tree_sitter_javascript.language()))
    functions = []
    for script in collector.scripts:
        for statement in parser.parse(script.encode()).root_node.named_children:
            name = statement.child_by_field_name("name")
            if statement.type == "function_declaration" and name and name.text == b"fmtTime":
                functions.append((statement.text or b"").decode())
    assert len(functions) == 1
    harness = (
        "const payload=JSON.parse(require('fs').readFileSync(0,'utf8'));"
        "const document={getElementById:()=>({dataset:{timezone:payload.zone}})};"
        + functions[0]
        + "process.stdout.write(fmtTime(payload.value));"
    )
    result = subprocess.run(
        [node, "-e", harness],
        input=json.dumps({"zone": zone, "value": value}),
        text=True,
        capture_output=True,
        check=True,
        timeout=5,
        env={**os.environ, "TZ": "Pacific/Honolulu"},
    )
    for part in expected:
        assert part in result.stdout


def test_llm_view_formats_same_backend_call_without_altering_payload():
    import shutil
    import subprocess

    import tree_sitter_javascript
    from tree_sitter import Language, Parser

    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the UI behavior regression")
    collector = _InlineScriptCollector()
    collector.feed(DASHBOARD_HTML)
    parser = Parser(Language(tree_sitter_javascript.language()))
    functions = []
    for script in collector.scripts:
        for statement in parser.parse(script.encode()).root_node.named_children:
            name = statement.child_by_field_name("name")
            if (
                statement.type == "function_declaration"
                and name
                and name.text in (b"fmtTime", b"loadLLM")
            ):
                functions.append((statement.text or b"").decode())
    assert len(functions) == 2
    harness = (
        """
const payload=JSON.parse(require('fs').readFileSync(0,'utf8'));
const original=JSON.stringify(payload);
const elements=new Map();
const document={getElementById(id){
 if(!elements.has(id))elements.set(id,{textContent:'',innerHTML:'',style:{},dataset:{timezone:'Europe/Berlin'}});
 return elements.get(id);
}};
const fmt=String,esc=String;
const renderModelCacheStatus=()=>{};
const apiFetch=async(path,options)=>{
 if(path!=='/api/v1/dashboard/llm'||options)throw new Error('Unexpected product effect');
 return {json:async()=>payload};
};
"""
        + "\n".join(functions)
        + """
loadLLM().then(()=>process.stdout.write(JSON.stringify({
 text:document.getElementById('l-last-call').textContent,
 unchanged:JSON.stringify(payload)===original
}))).catch(()=>process.exit(1));
"""
    )
    result = subprocess.run(
        [node, "-e", harness],
        input=json.dumps(
            {
                "activity": {
                    "status": "idle",
                    "last_call": {
                        "task": "review",
                        "provider": "deepseek",
                        "model": "test-model",
                        "started_at": "2026-10-04T07:49:00+00:00",
                        "finished_at": "2026-10-04T07:49:40.754394+00:00",
                        "outcome": "response_received",
                    },
                }
            }
        ),
        text=True,
        capture_output=True,
        check=True,
        timeout=5,
    )
    result_view = json.loads(result.stdout)
    assert result_view["unchanged"] is True
    assert "09:49:00" in result_view["text"] and "09:49:40" in result_view["text"]
    assert "GMT+2" in result_view["text"] and "Europe/Berlin" in result_view["text"]
    assert "07:49" not in result_view["text"]


def test_setup_and_dashboard_share_passive_missing_project_status(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PROJECT_ROOT", raising=False)
    monkeypatch.setenv("SAMUEL_PROJECT_BINDING_REQUIRED", "1")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = MagicMock()
    config.get.side_effect = lambda key, default=None: (
        str(config_dir) if key == "agent.config_dir" else default
    )
    bus = Bus()
    bus.register_command("HealthCheck", lambda _: pytest.fail("passive GET ran active health"))
    srv = create_server(bus, host="127.0.0.1", port=0, config=config, authentication=False)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with _serve(srv):
        for _ in range(2):
            setup = json.loads(
                urllib.request.urlopen(_url(srv, "/api/v1/setup/status"), timeout=2).read()
            )
            health = json.loads(
                urllib.request.urlopen(_url(srv, "/api/v1/dashboard/health"), timeout=2).read()
            )
            assert setup["project"]["reason_code"] == "project_binding_missing"
            assert health["operational_readiness"]["status"] == "blocked"
            assert (
                health["operational_readiness"]["project"]["reason_code"]
                == "project_binding_missing"
            )
    after = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before


def test_llm_stored_and_process_snapshot_agree_across_authenticated_http_views(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from samuel.core.config import FileConfig

    monkeypatch.setenv("SAMUEL_API_KEY", "synthetic-dashboard-key")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-provider-secret")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "auth.json").write_bytes(
        (Path(__file__).parents[1] / "config/auth.json").read_bytes()
    )
    (config_dir / "agent.json").write_text(
        json.dumps({"config_dir": str(config_dir), "data_dir": str(tmp_path / "data")})
    )
    (config_dir / "llm.json").write_text(
        json.dumps(
            {
                "default": {"provider": "gemini", "fallbacks": []},
                "gemini": {"model": "synthetic-model"},
            }
        )
    )
    config = FileConfig(config_dir)
    bus = Bus()
    bus.llm_routing_summary = {
        "default": "gemini",
        "default_source": "config",
        "fallbacks": [],
        "tasks": {"planning": "claude"},
    }
    events: list[Event] = []
    bus.subscribe("*", events.append)
    srv = create_server(bus, host="127.0.0.1", port=0, config=config, configuration_mode="setup")

    def request(path: str, payload: dict | None = None) -> dict:
        req = urllib.request.Request(
            _url(srv, path),
            data=None if payload is None else json.dumps(payload).encode(),
            headers={
                "Authorization": "Bearer synthetic-dashboard-key",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=2) as response:
            raw = response.read()
        assert b"synthetic-provider-secret" not in raw
        result = json.loads(raw)
        data = result.get("data", result)
        assert isinstance(data, dict)
        return data

    with _serve(srv):
        result = request(
            "/api/v1/settings/llm/global", {"provider": "deepseek", "fallbacks": ["ollama"]}
        )
        assert result["updated"] is True
        settings = request("/api/v1/dashboard/settings")
        status = request("/api/v1/dashboard/status")
        llm = request("/api/v1/dashboard/llm")
    global_config = settings["llm_global_config"]
    tile = next(row for row in status["tiles"] if row["key"] == "llm")
    assert global_config["provider"] == "deepseek"
    assert global_config["effective_provider"] == tile["value"] == llm["provider"] == "gemini"
    assert global_config["provider_source"] == tile["source"] == "config"
    assert global_config["restart_required"] and tile["restart_required"]
    assert (
        status["configuration"]["effective_config_digest"]
        == settings["configuration"]["effective_config_digest"]
    )
    assert status["build"]["revision"] == __build_info__.revision
    assert llm["activity"]["status"] == "unknown"
    assert config.get("llm.default.provider") == "gemini"
    assert events == []


@pytest.mark.parametrize("adapter_fact", [True, False])
def test_delivered_settings_js_separates_stored_default_from_process_fact(adapter_fact):
    import shutil
    import subprocess

    import tree_sitter_javascript
    from tree_sitter import Language, Parser

    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the UI behavior regression")
    collector = _InlineScriptCollector()
    collector.feed(DASHBOARD_HTML)
    parser = Parser(Language(tree_sitter_javascript.language()))
    functions = []
    for script in collector.scripts:
        for statement in parser.parse(script.encode()).root_node.named_children:
            name = statement.child_by_field_name("name")
            if statement.type == "function_declaration" and name and name.text == b"loadSettings":
                functions.append((statement.text or b"").decode())
    assert len(functions) == 1
    harness = (
        """
const payload=JSON.parse(require('fs').readFileSync(0,'utf8'));
const elements=new Map();
const document={getElementById(id){
 if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',style:{},querySelectorAll(){return [];}});
 return elements.get(id);
}};
const window={};
const esc=value=>String(value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
function loadDlq(){} function loadIdentityPanel(){}
async function apiFetch(path){return {json:async()=>path.includes('/settings')?payload:{transfer_warnings:[]}};}
"""
        + functions[0]
        + """
loadSettings().then(()=>process.stdout.write(JSON.stringify({html:elements.get('set-llm-global').innerHTML}))).catch(e=>{process.stderr.write(String(e));process.exit(1);});
"""
    )
    payload = {
        "configuration": {"writable": False, "restart_required": True},
        "llm_global_config": {
            "provider": "deepseek",
            "effective_provider": "gemini",
            "provider_source": "config",
            "effective_status": "runtime_adapter" if adapter_fact else "process_configuration",
            "restart_required": True,
            "fallbacks": ["ollama"],
            "providers": ["gemini", "deepseek"],
        },
    }
    result = subprocess.run(
        [node, "-e", harness],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
        timeout=5,
    )
    html = json.loads(result.stdout)["html"]
    assert "Prozessdefault</label><div><strong>gemini</strong>" in html
    assert 'value="deepseek" selected' in html
    assert "Gespeicherter Default" in html and "Gespeicherte Fallback-Kette" in html
    assert "Neustart ausstehend" in html
    assert ("Adapter erzeugt; Nutzung nur durch Call-Facts belegt." in html) is adapter_fact
    assert ("kein Adapter-Nachweis" in html) is not adapter_fact


@pytest.mark.parametrize("mode", ["setup", "production"])
def test_authenticated_prompt_http_never_reads_or_lists_external_symlinks(
    tmp_path, monkeypatch, mode
):
    from unittest.mock import MagicMock

    key = "synthetic-prompt-test-credential"
    monkeypatch.setenv("SAMUEL_API_KEY", key)
    directory = tmp_path / "config/llm/prompts"
    directory.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "external.md").write_text("PRIVATE")
    (directory / "provider").symlink_to(outside, target_is_directory=True)
    (outside / "test").mkdir()
    victim = outside / "test/external.md"
    victim.write_text("PRIVATE")
    config = MagicMock()
    config.get.side_effect = lambda k, d=None: (
        str(tmp_path / "config") if k == "agent.config_dir" else d
    )
    auth_root = tmp_path / "config"
    (auth_root / "auth.json").write_text(
        (Path(__file__).parents[1] / "config/auth.json").read_text(), encoding="utf-8"
    )
    srv = create_server(Bus(), host="127.0.0.1", port=0, config=config, configuration_mode=mode)
    with _serve(srv):
        for path in [
            "/api/v1/dashboard/llm/prompts/external.md?scope=provider:test",
            "/api/v1/dashboard/llm/prompts?scope=provider:test",
        ]:
            request = urllib.request.Request(_url(srv, path), headers={"X-API-Key": key})
            with urllib.request.urlopen(request, timeout=2) as response:
                body = json.loads(response.read())
            assert body.get("content", "") == ""
            assert body.get("prompts", []) == []
        for method in ["POST", "DELETE"]:
            path = "/api/v1/dashboard/llm/prompts/external.md"
            if method == "DELETE":
                path += "?scope=provider:test"
            request = urllib.request.Request(
                _url(srv, path),
                method=method,
                data=json.dumps({"content": "ATTACK", "scope": "provider:test"}).encode()
                if method == "POST"
                else None,
                headers={"X-API-Key": key, "Content-Type": "application/json"},
            )
            with pytest.raises(urllib.error.HTTPError) as failure:
                urllib.request.urlopen(request, timeout=2)
            assert failure.value.code == (409 if mode == "production" else 400)
    assert victim.read_text() == "PRIVATE"


@pytest.mark.parametrize("field", ["default", "provider", "schedule"])
def test_setup_http_rejects_external_prompt_filename_before_persisting(
    tmp_path, monkeypatch, field
):
    from unittest.mock import MagicMock

    key = "synthetic-prompt-test-credential"
    monkeypatch.setenv("SAMUEL_API_KEY", key)
    config = MagicMock()
    config.get.side_effect = lambda k, d=None: str(tmp_path) if k == "agent.config_dir" else d
    payload: dict[str, object] = {"system_prompt": "/tmp/private.md"}
    if field == "provider":
        payload = {"system_prompt_by_provider": {"deepseek": "/tmp/private.md"}}
    if field == "schedule":
        payload = {
            "schedule": {
                "active": True,
                "from": "00:00",
                "to": "23:59",
                "provider": "deepseek",
                "model": "test",
                "system_prompt": "/tmp/private.md",
            }
        }
    (tmp_path / "auth.json").write_text(
        (Path(__file__).parents[1] / "config/auth.json").read_text(), encoding="utf-8"
    )
    srv = create_server(Bus(), host="127.0.0.1", port=0, config=config, configuration_mode="setup")
    with _serve(srv):
        request = urllib.request.Request(
            _url(srv, "/api/v1/settings/llm/task"),
            method="POST",
            data=json.dumps({"task": "planning", "config": payload}).encode(),
            headers={"X-API-Key": key, "Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as failure:
            urllib.request.urlopen(request, timeout=2)
        assert failure.value.code == 400
    assert not (tmp_path / "llm/defaults.json").exists()


@pytest.mark.parametrize("mode", ["setup", "production"])
@pytest.mark.parametrize("catalog", ["missing", "stale", "unreachable"])
def test_task_and_schedule_save_do_not_consult_catalog(tmp_path, monkeypatch, mode, catalog):
    from unittest.mock import MagicMock

    from samuel.adapters.llm import costs

    monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
    config = MagicMock()
    config.get.side_effect = lambda k, d=None: str(tmp_path) if k == "agent.config_dir" else d

    def forbidden_catalog(*args, **kwargs):
        raise AssertionError("Saving must not consult the " + catalog + " catalog")

    monkeypatch.setattr(costs, "get_models_for_provider", forbidden_catalog)
    monkeypatch.setattr(costs, "get_pricing_info", forbidden_catalog)
    bus = Bus()
    srv = create_server(
        bus, host="127.0.0.1", port=0, config=config, configuration_mode=mode, authentication=False
    )
    payload = {
        "task": "planning",
        "config": {
            "provider": "openai",
            "model": "new-manual-model-id",
            "schedule": {
                "active": True,
                "from": "22:00",
                "to": "06:00",
                "provider": "deepseek",
                "model": "removed-from-catalog-id",
            },
        },
    }
    with _serve(srv):
        request = urllib.request.Request(
            _url(srv, "/api/v1/settings/llm/task"),
            method="POST",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        if mode == "production":
            with pytest.raises(urllib.error.HTTPError) as failure:
                urllib.request.urlopen(request, timeout=2)
            assert failure.value.code == 409
        else:
            result = json.loads(urllib.request.urlopen(request, timeout=2).read())
            assert result["updated"] is True
    path = tmp_path / "llm/defaults.json"
    if mode == "production":
        assert not path.exists()
    else:
        saved = json.loads(path.read_text())["tasks"]["planning"]
        assert saved["model"] == "new-manual-model-id"
        assert saved["schedule"]["model"] == "removed-from-catalog-id"


def test_task_and_schedule_markup_keep_free_input_and_valid_inline_handlers():
    import tree_sitter_javascript
    from tree_sitter import Language, Parser

    class Fields(HTMLParser):
        def __init__(self):
            super().__init__()
            self.inputs = {}
            self.handlers = []

        def handle_starttag(self, tag, attrs):
            data = dict(attrs)
            if tag == "input":
                self.inputs[data.get("id")] = data
            self.handlers.extend(value for key, value in attrs if key.startswith("on") and value)

    observed = _run_suggestion_ui(
        {},
        r"""
(async()=>{
 await openLLMTaskEditor('planning');
 process.stdout.write(JSON.stringify({html:document.getElementById('llm-edit-planning').innerHTML}));
})().catch(error=>{process.stderr.write(String(error));process.exitCode=1;});
""",
    )
    fields = Fields()
    fields.feed(observed["html"])
    assert fields.inputs["ed-model-planning"]["value"] == "custom-unknown-model"
    assert fields.inputs["ed-sch-model-planning"]["value"] == "saved-schedule-model"
    assert fields.inputs["ed-model-planning"]["list"] == "ed-models-planning"
    assert fields.inputs["ed-sch-model-planning"]["list"] == "ed-sch-models-planning"
    parser = Parser(Language(tree_sitter_javascript.language()))
    assert fields.handlers
    for handler in fields.handlers:
        assert not parser.parse(handler.encode()).root_node.has_error, handler


def test_passive_http_exposes_persisted_writer_failure_without_probe(tmp_path, monkeypatch):
    from samuel.adapters.state.sqlite import SQLiteStateStore
    from samuel.core.health_projection import record_audit_writer

    monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
    state = SQLiteStateStore(tmp_path)
    record_audit_writer(
        state.projections,
        instance_uuid=state.status().authority_instance,
        writer_id="sha256:test-writer",
        process_uuid="writer",
        state="write_failed",
        primary_error="append_refused",
        fallback_error="no_space",
    )
    bus = Bus()
    bus.state_store = SQLiteStateStore(tmp_path)
    bus.run_projection_store = bus.state_store.projections
    bus.register_command("HealthCheck", lambda _: pytest.fail("passive GET ran active health"))
    before = state.projections.list_projections()
    srv = create_server(bus, host="127.0.0.1", port=0, authentication=False)
    with _serve(srv):
        for _ in range(2):
            observed = json.loads(
                urllib.request.urlopen(_url(srv, "/api/v1/dashboard/health"), timeout=2).read()
            )
            assert observed["audit_writer"]["status"] == "loss_detected"
            assert observed["audit_writer"]["writers"][0]["summary"]["lost_events"] == 1
    assert state.projections.list_projections() == before


@pytest.mark.parametrize(
    "status,label",
    [
        ("written", "Letzter Write erfolgreich"),
        ("degraded", "Hauptpfad gestört, Ersatzpfad genutzt"),
        ("loss_detected", "Ereignisverlust festgestellt"),
        ("unknown", "Nicht aktuell geprüft"),
    ],
)
def test_audit_writer_ui_renders_distinct_states_and_escapes_details(status, label):
    import shutil
    import subprocess

    import tree_sitter_javascript
    from tree_sitter import Language, Parser

    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the UI behavior regression")
    parser = Parser(Language(tree_sitter_javascript.language()))
    collector = _InlineScriptCollector()
    collector.feed(DASHBOARD_HTML)
    functions = []
    for script in collector.scripts:
        for statement in parser.parse(script.encode()).root_node.named_children:
            name = statement.child_by_field_name("name")
            if name and name.text in {b"auditWriterLabel", b"renderAuditWriter"}:
                functions.append((statement.text or b"").decode())
    assert len(functions) == 2
    harness = (
        """
const payload=JSON.parse(require('fs').readFileSync(0,'utf8'));
const esc=value=>String(value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
const fmt=value=>String(value);const fmtTime=value=>String(value);
"""
        + "\n".join(functions)
        + "\nprocess.stdout.write(renderAuditWriter(payload));"
    )
    result = subprocess.run(
        [node, "-e", harness],
        input=json.dumps(
            {
                "status": status,
                "writers": [
                    {
                        "status": status,
                        "summary": {
                            "writer_id": "<script>alert(1)</script>",
                            "last_write": "primary_written",
                            "lost_events": 2,
                            "last_failure": {"state": "<img src=x onerror=x>"},
                        },
                    }
                ],
            }
        ),
        text=True,
        capture_output=True,
        check=True,
        timeout=5,
    )
    assert label in result.stdout
    assert "verloren 2" in result.stdout
    assert "<script>" not in result.stdout
    assert "<img src" not in result.stdout
