from __future__ import annotations

import json
from pathlib import Path

import pytest

from samuel.core.bus import Bus
from samuel.core.project_binding import (
    PROJECT_REQUEST_FILE,
    read_project_request,
    validate_project_request,
)
from samuel.slices.setup.handler import SetupHandler
from samuel.slices.setup.tests.test_handler import TestSetupHandler as SetupFixture


@pytest.fixture
def preparation(tmp_path: Path, monkeypatch):
    SetupFixture._clear_setup_env(monkeypatch)
    monkeypatch.setenv("SAMUEL_CONFIGURATION_MODE", "setup")
    monkeypatch.setenv("SAMUEL_PROJECT_BINDING_REQUIRED", "1")
    handler = SetupHandler(
        Bus(),
        project_root=tmp_path,
        scm_tester=lambda *_: {
            "valid": True,
            "repository": "https://scm.example.test/owner/project",
        },
    )
    payload = SetupFixture._dashboard_payload(
        llm_provider="manual",
        project_host_source="/srv/project-fixture",
        project_root="/projects/fixture",
        project_initial_revision="a" * 40,
    )
    return handler, payload


def test_preparation_persists_data_without_registration_or_host_probe(preparation, tmp_path: Path):
    handler, payload = preparation
    result = handler.configure_dashboard(payload)
    assert result["configured"] and result["project_prepared"]
    request = read_project_request(tmp_path / "config")
    assert request is not None
    assert request["host_source"] == "/srv/project-fixture"
    assert request["repository"] == "https://scm.example.test/owner/project"
    assert "PROJECT_ROOT=" not in (tmp_path / ".env").read_text()
    assert not (tmp_path / "config/project-binding.json").exists()
    assert not (tmp_path / "compose").exists()
    assert (tmp_path / "config" / PROJECT_REQUEST_FILE).stat().st_mode & 0o777 == 0o600
    status = handler.dashboard_status()["project_preparation"]
    assert status["status"] == "prepared" and status["host_checks"] == "not_verified"
    assert not status["registration_performed"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project_host_source", "../elsewhere"),
        ("project_host_source", "/srv/../secrets"),
        ("project_root", "/app/config"),
        ("project_root", "/var/run/docker.sock"),
        ("project_initial_revision", "main"),
        ("project_initial_revision", "1234"),
    ],
)
def test_invalid_preparation_leaves_existing_config_unchanged(
    preparation, tmp_path: Path, field, value
):
    handler, payload = preparation
    assert handler.configure_dashboard(payload)["configured"]
    paths = [
        tmp_path / ".env",
        tmp_path / "config/llm.json",
        tmp_path / "config" / PROJECT_REQUEST_FILE,
    ]
    before = {p: p.read_bytes() for p in paths}
    result = handler.configure_dashboard({**payload, field: value, "llm_model": "must-not-save"})
    assert not result["configured"]
    assert all(p.read_bytes() == content for p, content in before.items())


def test_production_cannot_prepare_or_rewrite_host_data(preparation, tmp_path: Path, monkeypatch):
    handler, payload = preparation
    assert handler.configure_dashboard(payload)["configured"]
    path = tmp_path / "config" / PROJECT_REQUEST_FILE
    before = path.read_bytes()
    monkeypatch.setenv("SAMUEL_CONFIGURATION_MODE", "production")
    production = SetupHandler(Bus(), project_root=tmp_path)
    result = production.configure_dashboard({**payload, "project_host_source": "/other"})
    assert result["code"] == "configuration_frozen"
    assert path.read_bytes() == before


def test_request_cannot_inject_execution_or_authority_fields(preparation, tmp_path: Path):
    handler, payload = preparation
    assert handler.configure_dashboard(payload)["configured"]
    request = read_project_request(tmp_path / "config")
    assert request is not None
    for key in ("command", "approved", "image", "mounts"):
        with pytest.raises(ValueError, match="schema"):
            validate_project_request({**request, key: "untrusted"})


def test_invalid_or_linked_request_is_visible_and_not_followed(preparation, tmp_path: Path):
    handler, _ = preparation
    (tmp_path / "config").mkdir()
    path = tmp_path / "config" / PROJECT_REQUEST_FILE
    path.write_text("not json")
    assert handler.dashboard_status()["project_preparation"]["status"] == "invalid"
    path.unlink()
    outside = tmp_path / "outside"
    outside.write_text("{}")
    path.symlink_to(outside)
    assert handler.dashboard_status()["project_preparation"]["status"] == "invalid"
    assert json.loads(outside.read_bytes()) == {}


def test_clearing_host_field_removes_only_unregistered_preparation(preparation, tmp_path: Path):
    handler, payload = preparation
    assert handler.configure_dashboard(payload)["configured"]
    result = handler.configure_dashboard({**payload, "project_host_source": ""})
    assert result["configured"] and result["project_preparation_cleared"]
    assert read_project_request(tmp_path / "config") is None
    assert "PROJECT_ROOT=" not in (tmp_path / ".env").read_text()


def test_failed_removal_rolls_back_other_configuration(preparation, tmp_path: Path, monkeypatch):
    handler, payload = preparation
    assert handler.configure_dashboard(payload)["configured"]
    paths = [
        tmp_path / ".env",
        tmp_path / "config/llm.json",
        tmp_path / "config" / PROJECT_REQUEST_FILE,
    ]
    before = {p: p.read_bytes() for p in paths}
    original = Path.unlink

    def deny_request(path, *args, **kwargs):
        if path == paths[-1]:
            raise PermissionError("fixture: no deletion")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_request)
    result = handler.configure_dashboard(
        {**payload, "project_host_source": "", "llm_model": "must-roll-back"}
    )
    assert not result["configured"]
    assert all(p.read_bytes() == content for p, content in before.items())


@pytest.mark.parametrize("kind", ["oversized", "fifo"])
def test_request_reader_rejects_unbounded_or_blocking_input(preparation, tmp_path: Path, kind):
    import os

    handler, _ = preparation
    (tmp_path / "config").mkdir()
    path = tmp_path / "config" / PROJECT_REQUEST_FILE
    if kind == "fifo":
        os.mkfifo(path)
    else:
        path.write_bytes(b" " * 65537)
    assert handler.dashboard_status()["project_preparation"]["status"] == "invalid"


@pytest.mark.parametrize("mode", ["setup", "production"])
def test_http_preparation_requires_identity_role_csrf_and_setup(
    preparation, tmp_path: Path, monkeypatch, mode
):
    import urllib.error
    import urllib.request
    from http.cookiejar import CookieJar

    from samuel.adapters.auth.local import LocalIdentityService
    from samuel.server import create_server
    from tests.test_server_identity import _csrf, _login, _runtime, _serve, _url

    _, payload = preparation
    bus, config = _runtime(tmp_path)
    identity = LocalIdentityService(
        bus.state_store.identity, instance_uuid=lambda: bus.state_store.status().authority_instance
    )
    admin = identity.login("admin", "administrator-password", client_key="fixture")
    identity.create_user(admin.actor, "operator", "operator-password-long", ("operator",))
    probes = []

    def probe(*args):
        probes.append(args)
        return {"valid": True, "repository": "https://scm.example.test/owner/project"}

    server = create_server(
        bus,
        host="127.0.0.1",
        port=0,
        config=config,
        configuration_mode=mode,
        setup_scm_tester=probe,
    )
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def post(csrf=False):
        headers = {"Content-Type": "application/json"}
        if csrf:
            headers["X-CSRF-Token"] = _csrf(jar)
        request = urllib.request.Request(
            _url(server, "/api/v1/setup/configure"),
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        try:
            response = opener.open(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        return response.status, json.loads(response.read())

    with _serve(server):
        assert post()[0] == 401
        _login(opener, server, "viewer", "viewer-password-long")
        assert post(True)[0] == 403
        _login(opener, server, "operator", "operator-password-long")
        assert post()[0] == 403
        assert post(True)[0] == 403
        _login(opener, server, "admin", "administrator-password")
        assert post()[0] == 403
        assert not probes
        status, result = post(True)
        assert status == (200 if mode == "setup" else 409), result
        if mode == "setup":
            assert result.get("data", result)["project_prepared"]
            response = json.loads(
                opener.open(_url(server, "/api/v1/setup/status"), timeout=5).read()
            )
            assert (
                response.get("data", response)["project_preparation"]["host_checks"]
                == "not_verified"
            )
        else:
            assert not probes
            assert not (tmp_path / "config" / PROJECT_REQUEST_FILE).exists()
    bus.close()


def test_existing_binding_cannot_be_replaced_by_preparation(preparation, tmp_path: Path):
    import hashlib

    from samuel.core.project_binding import (
        PROJECT_BINDING_SCHEMA,
        project_overlay,
        validate_binding,
    )

    handler, payload = preparation
    (tmp_path / "config").mkdir()
    binding = validate_binding(
        {
            "schema": PROJECT_BINDING_SCHEMA,
            "profile": "local-reference",
            "host_source": "/srv/existing",
            "container_target": "/projects/fixture",
            "repository": "https://scm.example.test/owner/project",
            "initial_revision": "b" * 40,
            "uid": 10001,
            "gid": 10001,
            "installation_sha256": "c" * 64,
            "compose_sha256": hashlib.sha256(
                project_overlay("/srv/existing", "/projects/fixture").encode()
            ).hexdigest(),
            "source_identity": {"device": 1, "inode": 2},
        }
    )
    path = tmp_path / "config/project-binding.json"
    path.write_text(json.dumps(binding))
    before = path.read_bytes()
    result = handler.configure_dashboard(payload)
    assert not result["configured"] and any("single project" in error for error in result["errors"])
    assert path.read_bytes() == before
    assert not (tmp_path / "config" / PROJECT_REQUEST_FILE).exists()


@pytest.mark.parametrize("cleared", [False, True])
def test_dashboard_clears_inactive_project_fields_after_confirmed_removal(cleared):
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
            (statement.text or b"").decode()
            for statement in tree.root_node.named_children
            if statement.type == "function_declaration"
            and (name := statement.child_by_field_name("name")) is not None
            and name.text == b"saveSetupWizard"
        )
    assert len(functions) == 1
    harness = (
        """
const cleared=JSON.parse(require('fs').readFileSync(0,'utf8'));
const elements=new Map();
const document={getElementById(id){if(!elements.has(id))elements.set(id,{value:'old input',textContent:'',style:{},disabled:false,checked:false});return elements.get(id)}};
let setupWritable=true,authMode='local_identity';
const setupValue=id=>document.getElementById(id).value;
const showToast=()=>{};
const loadSetupWizard=async()=>{};
const apiFetch=async(path,options)=>{
 if(path!=='/api/v1/setup/configure'||options.method!=='POST')throw Error('unexpected request');
 return {ok:true,status:200,json:async()=>({configured:true,project_preparation_cleared:cleared})};
};
"""
        + functions[0]
        + """
saveSetupWizard().then(()=>process.stdout.write(JSON.stringify({
 root:document.getElementById('setup-project-root').value,
 host:document.getElementById('setup-project-host').value,
 revision:document.getElementById('setup-project-revision').value,
 message:document.getElementById('setup-result').textContent
}))).catch(e=>{console.error(e);process.exit(1)});
"""
    )
    result = subprocess.run(
        [node, "-e", harness],
        input=json.dumps(cleared),
        text=True,
        capture_output=True,
        check=True,
        timeout=5,
    )
    view = json.loads(result.stdout)
    assert all(
        view[key] == ("" if cleared else "old input") for key in ("host", "root", "revision")
    )
    assert ("wurde verworfen" in view["message"]) is cleared
