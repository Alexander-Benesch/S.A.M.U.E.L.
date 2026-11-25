from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from tests.test_container_bootstrap import bootstrap as bootstrap
from tests.test_container_init import IMAGE, _inputs
from tools.container_init import (
    ContainerInitError,
    initialize,
    installed_operator_inputs,
    prepare_bootstrap,
)


@pytest.fixture
def installed_entry(bootstrap, tmp_path):
    if os.geteuid() != 0:
        pytest.skip("actual root-owned operator cache requires root")
    repository, profile, manifest, _, _ = bootstrap
    prepared = prepare_bootstrap(profile, repository.anchor, repository.cache, IMAGE)
    (tmp_path / "installation").mkdir()
    inputs = _inputs(tmp_path / "installation")
    inputs.update(
        manifest=manifest,
        manifest_sha256=prepared[1],
        owner=(10001, 10001),
        host_log_root="/var/log/samuel",
        host_backup_root="/srv/samuel/backups",
        port=19873,
        project="existing-single-project",
    )
    initialize(**inputs)
    arguments = dict(
        profile_path=profile,
        root_path=repository.anchor,
        receipt_path=inputs["config_root"] / ".container-install.json",
        cache=repository.cache,
        host_root="/",
        image=IMAGE,
    )
    return arguments, prepared


def test_existing_operator_selection_uses_installed_bindings_without_writes(installed_entry):
    args, prepared = installed_entry
    paths = [args["receipt_path"], *args["cache"].rglob("*")]
    before = {
        str(p): (
            p.stat().st_ino,
            p.stat().st_mtime_ns,
            p.stat().st_ctime_ns,
            hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None,
        )
        for p in paths
    }
    assert installed_operator_inputs(**args) == [
        *prepared[:4],
        IMAGE,
        "19873",
        "existing-single-project",
    ]
    after = {
        str(p): (
            p.stat().st_ino,
            p.stat().st_mtime_ns,
            p.stat().st_ctime_ns,
            hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None,
        )
        for p in [args["receipt_path"], *args["cache"].rglob("*")]
    }
    assert after == before


@pytest.mark.parametrize(
    "failure",
    [
        "manifest-bytes",
        "archive-bytes",
        "kit-bytes",
        "kit-symlink",
        "archive-symlink",
        "manifest-parent-symlink",
        "ambiguous-manifest",
        "receipt-revision",
        "root",
        "image",
        "cache-writable",
        "kit-writable",
        "foreign-owner",
        "missing-cache",
        "missing-kit",
    ],
)
def test_invalid_existing_inputs_cannot_produce_operator_handoff(installed_entry, failure):
    args, prepared = installed_entry
    cache = args["cache"]
    manifest, archive, kit = (cache / prepared[i] for i in (0, 2, 3))
    if failure.endswith("-bytes"):
        path = {
            "manifest-bytes": manifest,
            "archive-bytes": archive,
            "kit-bytes": kit / "tools/samuel-container",
        }[failure]
        path.write_bytes(path.read_bytes() + b"changed")
    elif failure in {"kit-symlink", "archive-symlink", "manifest-parent-symlink"}:
        path = {
            "kit-symlink": kit,
            "archive-symlink": archive,
            "manifest-parent-symlink": manifest.parent,
        }[failure]
        moved = path.with_name(path.name + "-original")
        path.rename(moved)
        path.symlink_to(moved, target_is_directory=moved.is_dir())
    elif failure == "ambiguous-manifest":
        (manifest.parent / "another.json").write_text("{}")
    elif failure == "receipt-revision":
        data = json.loads(args["receipt_path"].read_bytes())
        data["revision"] = "c" * 40
        args["receipt_path"].write_text(json.dumps(data))
    elif failure == "root":
        args["root_path"].write_text("unbound root")
    elif failure == "image":
        args["image"] = "another@sha256:" + "b" * 64
    elif failure == "cache-writable":
        cache.chmod(0o777)
    elif failure == "kit-writable":
        (kit / "tools").chmod(0o777)
    elif failure == "foreign-owner":
        os.chown(archive, 10001, 10001)
    elif failure == "missing-cache":
        args["cache"] = cache.parent / "absent"
    else:
        kit.rename(kit.with_name("saved-kit"))
    with pytest.raises(ContainerInitError):
        installed_operator_inputs(**args)
    if failure == "missing-cache":
        assert not args["cache"].exists()
    if failure == "missing-kit":
        assert not kit.exists()


def shell_entry(tmp_path: Path, operation: str, *, invalid: str = ""):
    import shutil
    import subprocess
    import sys

    from tests.test_container_init import ROOT

    package = tmp_path / "package"
    (package / "tools").mkdir(parents=True)
    for name in ("samuel-container", "container_init.py"):
        shutil.copyfile(ROOT / "tools" / name, package / "tools" / name)
    (package / "bootstrap-profile.json").write_text(json.dumps({"bootstrap_image": IMAGE}))
    (package / "trusted-root.json").write_text("fixture root; actual validator tested separately")
    host = tmp_path / "host"
    receipt = host / "etc/samuel/.container-install.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("fixture receipt; actual reader tested separately")
    cache = host / "srv/samuel/release-cache"
    kit = cache / ("installers/" + "a" * 64)
    (kit / "tools").mkdir(parents=True)
    output = tmp_path / "delegated.json"
    (kit / "tools/samuel-container").write_text(
        "#!/bin/bash\nexec "
        + sys.executable
        + " -c "
        + "'import json,sys;open(sys.argv[1],\"w\").write(json.dumps(sys.argv[2:]))' "
        + str(output)
        + ' "$@"\n'
    )
    response = [
        "SAMUEL_INSTALLED_OPERATOR",
        "artifacts/" + "b" * 64 + "/manifest.json",
        "b" * 64,
        "artifacts/" + "a" * 64 + "/samuel-oci-2.0.0a35.tar.gz",
        "installers/" + "a" * 64,
        IMAGE,
        "19873",
        "existing-single-project",
    ]
    if invalid == "path":
        response[4] = "../../untrusted"
    elif invalid == "image":
        response[5] = "samuel:latest"
    elif invalid == "extra":
        response.append("arbitrary host command")
    elif invalid == "port":
        response[6] = "7777; touch escaped"
    elif invalid == "port-range":
        response[6] = "99999"
    elif invalid == "marker":
        response[0] = "UNVERIFIED"
    binary = tmp_path / "bin"
    binary.mkdir()
    trace = tmp_path / "docker.jsonl"
    docker = binary / "docker"
    docker.write_text(
        f"#!{sys.executable}\nimport json,sys\na=sys.argv[1:]\n"
        + f"with open({str(trace)!r},'a') as f:f.write(json.dumps(a)+'\\n')\n"
        + "if a[0]=='version':print('26.1.5')\n"
        + "elif a[0]=='info':print('linux/amd64')\n"
        + "elif a[:2]==['compose','version']:print('2.26.1')\n"
        + "elif a[0]=='pull':pass\n"
        + f"elif 'installed-operator' in a:print({chr(10).join(response)!r})\n"
        + "else:sys.exit(91)\n"
    )
    docker.chmod(0o755)
    command = ["bash", str(package / "tools/samuel-container"), operation, "--root", str(host)]
    if operation == "start":
        command += ["--approve-project", "c" * 64]
    command += ["--recover-maintenance", "yes"]
    result = subprocess.run(
        command,
        env={**os.environ, "PATH": f"{binary}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result, output, trace, host, cache


@pytest.mark.parametrize("operation", ["start", "setup"])
def test_short_operator_call_delegates_to_existing_installer_with_read_only_selection(
    tmp_path, operation
):
    result, output, trace, host, cache = shell_entry(tmp_path, operation)
    assert result.returncode == 0, result.stderr
    delegated = json.loads(output.read_text())
    assert delegated == [
        operation,
        "--manifest",
        str(cache / ("artifacts/" + "b" * 64 + "/manifest.json")),
        "--manifest-sha256",
        "b" * 64,
        "--installer-archive",
        str(cache / ("artifacts/" + "a" * 64 + "/samuel-oci-2.0.0a35.tar.gz")),
        "--image",
        IMAGE,
        "--root",
        str(host),
        "--port",
        "19873",
        "--project",
        "existing-single-project",
        "--recover-maintenance",
        "yes",
        *(["--approve-project", "c" * 64] if operation == "start" else []),
    ]
    calls = [json.loads(line) for line in trace.read_text().splitlines()]
    verifier = next(call for call in calls if "installed-operator" in call)
    assert verifier[verifier.index("--network") + 1] == "none"
    assert "--read-only" in verifier and "no-new-privileges" in verifier
    assert verifier[verifier.index("--cap-drop") + 1] == "ALL"
    mounts = [value for value in verifier if value.startswith("type=bind,")]
    assert len(mounts) == 5 and all(value.endswith(",readonly") for value in mounts)
    assert not any("docker.sock" in value or "/var/lib/samuel" in value for value in mounts)
    assert not any("prepare-bootstrap" in call or "up" in call for call in calls)


@pytest.mark.parametrize("failure", ["path", "image", "extra", "port", "port-range", "marker"])
def test_short_operator_rejects_malformed_handoff_without_host_action(tmp_path, failure):
    result, output, _, _, _ = shell_entry(tmp_path, "start", invalid=failure)
    assert result.returncode != 0 and "invalid installed operator receipt" in result.stderr
    assert not output.exists()


def test_profile_target_does_not_select_a_new_release_or_fetch_metadata(
    installed_entry, monkeypatch
):
    import samuel.release_trust as trust

    args, prepared = installed_entry
    profile = json.loads(args["profile_path"].read_bytes())
    profile["manifest_target"] = "releases/future/manifest.json"
    args["profile_path"].write_text(json.dumps(profile))

    def forbidden(**_kwargs):
        pytest.fail("a mode switch must not fetch or select an update")

    monkeypatch.setattr(trust, "fetch_release_inputs", forbidden)
    assert installed_operator_inputs(**args)[:4] == prepared[:4]
