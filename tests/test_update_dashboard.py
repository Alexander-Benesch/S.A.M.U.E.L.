from __future__ import annotations

import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from samuel.local_release import LocalReleaseError, OCIUpdatePreview
from samuel.release_trust import release_source_document
from tests.test_oci_update_preparation import _publish
from tests.test_oci_update_preparation import update_source as update_source
from tests.test_server_identity import _serve


@pytest.fixture
def preview(update_source, tmp_path: Path):
    repository, _, _, source = update_source
    _publish(update_source)
    calls: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.lstrip("/")
            calls.append(path)
            data = repository.files.get(path)
            self.send_response(200 if data is not None else 404)
            self.end_headers()
            self.wfile.write(data or b"")

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    value = json.loads(source.read_bytes())
    base = f"http://127.0.0.1:{server.server_port}"
    value["profile"].update(metadata_url=base + "/metadata/", targets_url=base + "/targets/")
    source.write_bytes(release_source_document(value["profile"], value["root"].encode(), "b" * 64))
    current = {
        "supported": True,
        "binding": {"version": "2.0.0a34", "state_schema": 10, "instance": "fixture"},
        "blockers": [],
        "external_blockers": [],
    }
    observations: list[bool] = []

    def snapshot(external: bool):
        observations.append(external)
        return copy.deepcopy(current)

    client = OCIUpdatePreview(source, tmp_path / "preview-cache", snapshot, 10)
    with _serve(server):
        yield client, current, calls, observations


def test_passive_preview_never_fetches_or_requests_external_blockers(preview):
    client, _, calls, observations = preview
    status = client.status()
    assert status["source"] == "configured"
    assert status["preparation"] is None
    assert status["operator_execution"] == "local_operator_required"
    assert status["operator_command"] is None
    assert not calls and observations == [False]
    assert not client.cache_dir.exists()


def test_preview_fetches_explicit_version_and_keeps_host_checks_open(preview):
    client, _, calls, observations = preview
    status = client.prepare("2.0.0a35")
    assert status["preparation"]["target_version"] == "2.0.0a35"
    assert status["preparation"]["artifact_count"] == 7
    assert not status["stale"] and not status["preparing"]
    assert observations == [True, False, False]
    assert "metadata/timestamp.json" in calls
    before = list(calls)
    client.status()
    assert calls == before
    assert "inputs" not in status["preparation"]
    assert status["host_checks"] == "not_verified"
    assert status["initial_handoff"] == "not_qualified_by_this_check"
    assert status["preparation"]["compatibility"]["operator_approval"] == "required"
    assert not status["installation_performed"]


@pytest.mark.parametrize("failure", ["source", "state"])
def test_prepared_view_becomes_stale_when_binding_changes(preview, failure):
    client, current, _, _ = preview
    client.prepare("2.0.0a35")
    if failure == "source":
        value = json.loads(client.source_path.read_bytes())
        value["profile"]["manifest_target_template"] = "changed/{version}/manifest.json"
        client.source_path.write_text(json.dumps(value))
    else:
        current["binding"]["instance"] = "other-installation"
    assert client.status()["stale"]


def test_runtime_blockers_remain_visible_without_invalidating_verified_bytes(preview):
    client, current, _, _ = preview
    current["external_blockers"] = ["Issue #17: status:approved"]
    client.prepare("2.0.0a35")
    current["blockers"] = ["Konfiguration aktiv"]
    status = client.status()
    assert status["current"]["blockers"] == ["Konfiguration aktiv"]
    assert status["preparation"]["external_blockers"] == ["Issue #17: status:approved"]
    assert status["host_checks"] == "not_verified"


def test_failed_repreparation_does_not_show_previous_attempt_as_success(preview):
    client, _, _, _ = preview
    client.prepare("2.0.0a35")
    with pytest.raises(RuntimeError, match="canonical"):
        client.prepare("latest")
    assert client.status()["preparation"] is None
    assert not client.status()["preparing"]


def test_concurrent_preparation_is_rejected_without_a_second_download(preview, monkeypatch):
    client, _, calls, _ = preview
    entered, release = threading.Event(), threading.Event()
    original = client.snapshot

    def snapshot(external):
        if external:
            entered.set()
            assert release.wait(5)
        return original(external)

    monkeypatch.setattr(client, "snapshot", snapshot)
    outcomes = []
    thread = threading.Thread(target=lambda: outcomes.append(client.prepare("2.0.0a35")))
    thread.start()
    try:
        assert entered.wait(5)
        assert client.status()["preparing"]
        with pytest.raises(LocalReleaseError, match="already running"):
            client.prepare("2.0.0a35")
        assert not calls
    finally:
        release.set()
        thread.join(10)
    assert len(outcomes) == 1 and not client.status()["preparing"]


def test_state_change_during_fetch_does_not_publish_a_prepared_view(preview, monkeypatch):
    import samuel.local_release as release

    client, current, _, _ = preview
    original = release.prepare_oci_update

    def changed(**kwargs):
        result = original(**kwargs)
        current["binding"]["instance"] = "changed"
        return result

    monkeypatch.setattr(release, "prepare_oci_update", changed)
    with pytest.raises(LocalReleaseError, match="changed"):
        client.prepare("2.0.0a35")
    assert client.status()["preparation"] is None


@pytest.mark.parametrize("source_state", ["missing", "unresolved", "invalid"])
def test_missing_or_invalid_source_has_no_implicit_fallback(preview, source_state):
    client, _, calls, _ = preview
    if source_state == "missing":
        client.source_path.unlink()
    elif source_state == "invalid":
        client.source_path.write_text("{}")
    else:
        value = json.loads(client.source_path.read_bytes())
        del value["profile"]["manifest_target_template"]
        client.source_path.write_text(json.dumps(value))
    assert client.status()["source"] == source_state
    with pytest.raises((OSError, RuntimeError)):
        client.prepare("2.0.0a35")
    assert not calls


def test_restarted_dashboard_requires_explicit_new_preparation(preview):
    client, _, _, _ = preview
    client.prepare("2.0.0a35")
    restarted = OCIUpdatePreview(client.source_path, client.cache_dir, client.snapshot, 10)
    assert restarted.status()["preparation"] is None


def test_actual_http_permissions_csrf_and_fixed_payload_in_production(
    preview, tmp_path, monkeypatch
):
    import dataclasses
    import urllib.error
    import urllib.request
    from http.cookiejar import CookieJar

    import samuel.server as module
    from samuel.core.configuration_session import ConfigurationSession
    from tests.test_server_identity import _csrf, _login, _runtime, _url

    client, _, calls, _ = preview
    runtime = tmp_path / "http-runtime"
    runtime.mkdir()
    bus, config = _runtime(runtime)
    session = ConfigurationSession(bus.state_store.authority)
    bus.configuration_session = session
    identity = module.LocalIdentityService(
        bus.state_store.identity, instance_uuid=lambda: bus.state_store.status().authority_instance
    )
    admin = identity.login("admin", "administrator-password", client_key="fixture").actor
    identity.create_user(admin, "operator", "operator-password-long", ("operator",))
    monkeypatch.setenv("SAMUEL_PROJECT_BINDING_REQUIRED", "1")
    monkeypatch.setattr(
        module,
        "__build_info__",
        dataclasses.replace(
            module.__build_info__, product_version="2.0.0a34", revision="a" * 40, dirty=False
        ),
    )
    (runtime / "config/release-source.json").write_bytes(client.source_path.read_bytes())
    server = module.create_server(
        bus, host="127.0.0.1", port=0, config=config, configuration_mode="production"
    )
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def request(*, post=False, csrf=False, body=None):
        path = "/api/v1/dashboard/update" + ("/prepare" if post else "")
        headers = {"Content-Type": "application/json"}
        if csrf:
            headers["X-CSRF-Token"] = _csrf(jar)
        req = urllib.request.Request(
            _url(server, path),
            data=json.dumps(body if body is not None else {"version": "2.0.0a35"}).encode()
            if post
            else None,
            headers=headers,
        )
        try:
            response = opener.open(req, timeout=10)
        except urllib.error.HTTPError as exc:
            response = exc
        return response.status, json.loads(response.read())

    before = session.state()
    with _serve(server):
        assert request()[0] == 401
        _login(opener, server, "viewer", "viewer-password-long")
        assert request()[0] == 403 and request(post=True, csrf=True)[0] == 403
        _login(opener, server, "admin", "administrator-password")
        assert request(post=True, csrf=True)[0] == 403  # Separate operational role.
        _login(opener, server, "operator", "operator-password-long")
        status, view = request()
        assert status == 200 and view["source"] == "configured"
        assert not calls
        assert request(post=True)[0] == 403
        for key in ["command", "image", "url", "approved"]:
            assert (
                request(post=True, csrf=True, body={"version": "2.0.0a35", key: "untrusted"})[0]
                == 400
            )
        assert not calls
        status, view = request(post=True, csrf=True)
        assert status == 200, view
        assert view["preparation"]["target_version"] == "2.0.0a35"
        assert view["operator_command"] is None
        assert any("Projektbindung" in reason for reason in view["current"]["blockers"])
        assert not view["installation_performed"]
        assert session.state() == before
        assert "metadata/timestamp.json" in calls
    bus.close()


@pytest.mark.parametrize("prepare", [False, True])
@pytest.mark.parametrize("ready", [False, True])
def test_delivered_javascript_parses_and_only_explicit_action_prepares(prepare, ready):
    import shutil
    import subprocess

    import tree_sitter_javascript
    from tree_sitter import Language, Parser

    from samuel.server import DASHBOARD_HTML
    from tests.test_server_dashboard import _InlineScriptCollector

    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for delivered UI regression")
    collector = _InlineScriptCollector()
    collector.feed(DASHBOARD_HTML)
    parser = Parser(Language(tree_sitter_javascript.language()))
    functions: list[str] = []
    for script in collector.scripts:
        tree = parser.parse(script.encode())
        assert not tree.root_node.has_error
        functions.extend(
            (s.text or b"").decode()
            for s in tree.root_node.named_children
            if s.type == "function_declaration"
            and (name := s.child_by_field_name("name")) is not None
            and name.text == b"loadUpdatePreview"
        )
    assert len(functions) == 1
    harness = (
        r"""
const {prepare,ready}=JSON.parse(require('fs').readFileSync(0,'utf8')),requests=[];
const nodes=new Map();
const document={getElementById(id){if(!nodes.has(id))nodes.set(id,{textContent:'',disabled:false,value:' 2.0.0a35 '});return nodes.get(id)}};
const apiFetch=async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>({source:'configured',current:{binding:{version:'2.0.0a34'},blockers:['<script>inert</script>']},preparation:{target_version:'2.0.0a35',manifest_sha256:'a'.repeat(64),artifact_count:7,external_blockers:[]},stale:!ready,operator_command:ready?'bash tools/samuel-container update --target 2.0.0a35':null})}};
"""
        + functions[0]
        + r"""
loadUpdatePreview(prepare).then(()=>process.stdout.write(JSON.stringify({requests,message:document.getElementById('update-status').textContent,disabled:document.getElementById('update-prepare').disabled})));
"""
    )
    result = subprocess.run(
        [node, "-e", harness],
        input=json.dumps({"prepare": prepare, "ready": ready}),
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(result.stdout)
    assert len(data["requests"]) == 1
    request = data["requests"][0]
    assert request["url"] == "/api/v1/dashboard/update" + ("/prepare" if prepare else "")
    if prepare:
        assert request["options"]["method"] == "POST"
        assert json.loads(request["options"]["body"]) == {"version": "2.0.0a35"}
    else:
        assert "options" not in request
    assert "<script>inert</script>" in data["message"]
    assert "nicht qualifiziert" in data["message"] and "keine Hostfreigabe" in data["message"]
    if ready:
        assert "bash tools/samuel-container update --target 2.0.0a35" in data["message"]
        assert "--root" in data["message"] and "Hostrechten" in data["message"]
    else:
        assert "veraltet" in data["message"] and "Kein Update ausgeführt" in data["message"]
    assert not data["disabled"]


@pytest.mark.parametrize("length,expected", [("-1", 400), ("invalid", 400), ("65537", 413)])
def test_update_request_rejects_unsafe_length_before_reading_body(tmp_path, length, expected):
    import http.client

    from samuel.server import create_server
    from tests.test_server_identity import _runtime

    bus, config = _runtime(tmp_path)
    server = create_server(bus, host="127.0.0.1", port=0, config=config)
    with _serve(server):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
        connection.putrequest("POST", "/api/v1/dashboard/update/prepare")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", length)
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == expected
        response.read()
        connection.close()
    bus.close()


@pytest.mark.parametrize(
    ("status", "version", "revision"),
    [
        ({"product_version": "2.0.0a35", "access": "viewer"}, "2.0.0a35", ""),
        (
            {"build": {"product_version": "2.0.0a34", "revision": "a" * 40}},
            "2.0.0a34",
            " · " + "a" * 12,
        ),
        ({}, "0+unknown", ""),
    ],
)
def test_delivered_version_header_accepts_existing_passive_identity_status(
    status, version, revision
):
    import shutil
    import subprocess

    import tree_sitter_javascript
    from tree_sitter import Language, Parser

    from samuel.server import DASHBOARD_HTML
    from tests.test_server_dashboard import _InlineScriptCollector

    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for delivered UI regression")
    collector = _InlineScriptCollector()
    collector.feed(DASHBOARD_HTML)
    parser = Parser(Language(tree_sitter_javascript.language()))
    functions: list[str] = []
    for script in collector.scripts:
        tree = parser.parse(script.encode())
        assert not tree.root_node.has_error
        functions.extend(
            (s.text or b"").decode()
            for s in tree.root_node.named_children
            if s.type == "function_declaration"
            and (name := s.child_by_field_name("name")) is not None
            and name.text == b"loadStatus"
        )
    assert len(functions) == 1
    harness = r"""
const status=JSON.parse(require('fs').readFileSync(0,'utf8'));
const nodes=new Map(),requests=[];
const document={getElementById(id){if(!nodes.has(id))nodes.set(id,{textContent:'',innerHTML:'',style:{}});return nodes.get(id);}};
const esc=String,fmt=String,renderAuditWriter=()=>'';
async function apiFetch(url){requests.push(url);return {json:async()=>url.endsWith('/status')?status:{}};}
loadStatus().then(()=>process.stdout.write(JSON.stringify({version:nodes.get('product-version').textContent,revision:nodes.get('build-revision').textContent,requests}))).catch(e=>{console.error(e);process.exit(1);});
"""
    result = subprocess.run(
        [node, "-e", functions[0] + harness],
        input=json.dumps(status),
        text=True,
        capture_output=True,
        check=True,
        timeout=5,
    )
    rendered = json.loads(result.stdout)
    assert rendered["version"] == version
    assert rendered["revision"] == revision
    assert rendered["requests"] == ["/api/v1/dashboard/status", "/api/v1/dashboard/health"]


@pytest.mark.parametrize("change", ["stale", "local_blocker", "external_blocker", "unsupported"])
def test_operator_guidance_is_hidden_when_preparation_no_longer_applies(preview, change):
    client, current, _, _ = preview
    prepared = client.prepare("2.0.0a35")
    assert prepared["operator_command"] == "bash tools/samuel-container update --target 2.0.0a35"
    if change == "stale":
        current["binding"]["instance"] = "changed"
    elif change == "local_blocker":
        current["blockers"] = ["workflow pending"]
    elif change == "external_blocker":
        current["external_blockers"] = ["SCM workflow pending"]
        client.prepare("2.0.0a35")
    else:
        current["supported"] = False
    assert client.status()["operator_command"] is None
