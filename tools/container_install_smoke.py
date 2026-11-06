#!/usr/bin/env python3
"""Qualify the published OCI operator path on a fresh Docker host (#970/#971).

Standard-library test harness; installation uses only the released installer.
No publisher smoke, source-mounted runtime, SCM workflow or LLM completion.
Existing operator credentials enter only through a protected test setup file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--installer-archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=19771)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--setup-config-file", type=Path, required=True)
    parser.add_argument("--compose-dir", type=Path)
    parser.add_argument("--command-timeout", type=int, default=1200)
    args = parser.parse_args()
    if args.setup_config_file.stat().st_mode & 0o077:
        raise RuntimeError("test setup config must be protected from group/other access")
    setup_values = json.loads(args.setup_config_file.read_text())
    if args.command_timeout < 60:
        raise RuntimeError("command timeout must be at least 60 seconds")
    if args.root != Path("/") and args.root.exists():
        raise RuntimeError("smoke requires a new, absent installation root")
    for relative in (
        "etc/samuel",
        "var/lib/samuel",
        "var/log/samuel",
        "srv/samuel/workspaces",
        "srv/samuel/backups",
    ):
        if (args.root / relative).exists():
            raise RuntimeError("smoke requires absent operator paths")
    manifest = json.loads(args.manifest.read_text())
    project = "samuel-971-" + str(int(time.time()))
    config = args.root / "etc/samuel"
    environment = {
        k: v for k, v in os.environ.items() if not k.startswith(("SAMUEL_", "SCM_", "COMPOSE_"))
    }
    result: dict[str, Any] = {
        "issues": [970, 971],
        "status": "FAILED",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "image": manifest["container"]["reference"],
        "manifest_sha256": args.manifest_sha256,
        "installer_archive_sha256": hashlib.sha256(args.installer_archive.read_bytes()).hexdigest(),
        "path": "published samuel-container install -> authenticated setup -> samuel-container start",
        "publisher_smoke_used": False,
        "workflow_started": False,
        "llm_completion_started": False,
    }

    def command(argv: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        with subprocess.Popen(
            argv,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        ) as process:
            try:
                stdout, stderr = process.communicate(timeout=args.command_timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate()
                raise RuntimeError("operator command timed out; process group terminated") from None
            cp = subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
        if check and cp.returncode:
            raise RuntimeError(f"operator command failed (exit {cp.returncode}): {argv[0]}")
        return cp

    def run(argv: list[str]) -> str:
        return command(argv).stdout

    options = [
        "--manifest",
        str(args.manifest),
        "--manifest-sha256",
        args.manifest_sha256,
        "--installer-archive",
        str(args.installer_archive),
        "--compose-dir",
        str(args.compose_dir or args.installer_archive.parent),
        "--root",
        str(args.root),
        "--port",
        str(args.port),
        "--project",
        project,
    ]
    launcher = ["bash", str(args.installer / "tools/samuel-container")]
    compose = [
        "docker",
        "compose",
        "--env-file",
        str(config / "compose.env"),
        "-f",
        str(config / "compose/docker-compose.yml"),
    ]
    api_key = ""

    def request(
        path: str, body: dict[str, Any] | None = None, *, authenticated: bool = True
    ) -> tuple[int, dict[str, Any]]:
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["X-API-Key"] = api_key
        req = urllib.request.Request(
            f"http://127.0.0.1:{args.port}{path}",
            headers=headers,
            data=None if body is None else json.dumps(body).encode(),
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)

    try:
        assert not run(["docker", "image", "ls", "--format", "{{.ID}}"]).strip(), (
            "fresh host must have an empty imagestore"
        )
        result["initial_image_count"] = 0
        result["daemon_version"] = run(
            ["docker", "version", "--format", "{{.Server.Version}}"]
        ).strip()
        result["compose_version"] = run(["docker", "compose", "version", "--short"]).strip()
        print("Running documented install on empty host", flush=True)
        output = run(launcher + ["install"] + options)
        assert "setup runtime ready" in output
        result["install"] = "PASS"
        binding = json.loads((config / ".container-install.json").read_text())
        # Native setup generates simple secret assignments; never record their values.
        for line in (config / ".env").read_text().splitlines():
            if line.startswith("SAMUEL_API_KEY="):
                api_key = line.split("=", 1)[1].strip().strip("\"'")
        assert api_key and (config / ".env").stat().st_mode & 0o777 == 0o600
        result["keys_generated_protected"] = True
        with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/", timeout=30) as response:
            html = response.read().decode()
            assert response.status == 200
        assert 'id="setup-scm-provider"' in html and 'id="setup-llm-provider"' in html
        assert api_key not in html
        result["setup_frontend_reachable_without_scm"] = "PASS"
        status, setup = request("/api/v1/setup/status")
        assert status == 200 and setup["configuration"]["mode"] == "setup"
        cid = run(compose + ["ps", "-q", "samuel"]).strip()
        inspected = json.loads(run(["docker", "inspect", cid]))[0]
        mounts = {x["Destination"]: x for x in inspected["Mounts"]}
        assert mounts["/app/config"]["RW"] and mounts["/app/.env"]["RW"]
        assert all(
            mounts[x]["RW"]
            for x in ("/app/data", "/samuel-workspaces", "/app/data/logs", "/app/data/backups")
        )
        assert mounts["/app/data/logs"]["Source"] == str(args.root / "var/log/samuel")
        assert mounts["/app/data/backups"]["Source"] == str(args.root / "srv/samuel/backups")
        result["setup_mounts_and_canonical_host_paths"] = "PASS"
        status, saved = request(
            "/api/v1/setup/configure",
            {**setup_values, "llm_provider": "manual", "llm_model": "installation-smoke"},
        )
        assert status == 200 and saved.get("configured") is True
        assert (
            json.loads((config / "config/llm.json").read_text())["default"]["provider"] == "manual"
        )
        task_defaults = config / "config/llm/defaults.json"
        for task in json.loads(task_defaults.read_text()).get("tasks", {}):
            status, updated = request(
                "/api/v1/settings/llm/task",
                {
                    "task": task,
                    "config": {
                        "provider": "manual",
                        "model": "installation-smoke",
                        "schedule": None,
                    },
                },
            )
            assert status == 200 and updated.get("updated") is True
        assert all(
            task.get("provider") == "manual" and task.get("model") == "installation-smoke"
            for task in json.loads(task_defaults.read_text()).get("tasks", {}).values()
        )
        result["all_task_routes_explicitly_configured_manual_via_api"] = "PASS"
        result["dashboard_persistence"] = "PASS"
        before = {
            p: p.read_bytes() for p in (config / "config/llm.json", task_defaults, config / ".env")
        }
        assert command(launcher + ["install"] + options, check=False).returncode != 0
        assert all(p.read_bytes() == v for p, v in before.items())
        result["repeated_install_blocks_preserves_sources"] = "PASS"
        print("Setup save verified; switching with documented start", flush=True)
        assert "production runtime ready" in run(launcher + ["start"] + options)
        cid = run(compose + ["ps", "-q", "samuel"]).strip()
        inspected = json.loads(run(["docker", "inspect", cid]))[0]
        mounts = {x["Destination"]: x for x in inspected["Mounts"]}
        assert not mounts["/app/config"]["RW"] and "/app/.env" not in mounts
        assert inspected["Config"]["Image"] == manifest["container"]["reference"]
        assert (
            run(compose + ["exec", "-T", "samuel", "samuel", "--version"]).strip()
            == "samuel " + manifest["version"]
        )
        status, dashboard = request("/api/v1/dashboard/status")
        assert (
            status == 200
            and dashboard["build"]["product_version"] == manifest["version"]
            and dashboard["build"]["revision"] == manifest["commit"]
        )
        result["runtime_identity"] = {
            "version": manifest["version"],
            "revision": manifest["commit"],
            "image": inspected["Config"]["Image"],
        }
        assert request("/api/v1/dashboard/status", authenticated=False)[0] == 401
        status, health = request("/api/v1/dashboard/health")
        assert status == 200 and health["healthy"] is True
        result["operational_readiness"] = health.get("operational_readiness", {}).get(
            "status", "unknown"
        )
        run(compose + ["exec", "-T", "samuel", "samuel", "health"])
        status, refused = request("/api/v1/setup/configure", {"llm_provider": "manual"})
        assert status == 409 and refused.get("code") == "configuration_frozen"
        assert all(p.read_bytes() == v for p, v in before.items())
        result["production_freeze_and_authentication"] = "PASS"
        run(launcher + ["init"] + options)
        assert all(p.read_bytes() == v for p, v in before.items())
        assert command(launcher + ["setup"] + options, check=False).returncode != 0
        result["idempotent_init_and_explicit_setup_guard"] = "PASS"
        marker = args.root / "srv/samuel/workspaces/installation-preservation-marker"
        marker.write_text("operator workspace retained\n")
        run(launcher + ["start"] + options)
        assert marker.read_text() == "operator workspace retained\n" and all(
            p.read_bytes() == v for p, v in before.items()
        )
        result["production_recreate_preserves_sources_and_workspace"] = "PASS"
        for _ in range(90):
            cid = run(compose + ["ps", "-q", "samuel"]).strip()
            state = json.loads(run(["docker", "inspect", cid]))[0]["State"]["Health"]["Status"]
            if state == "healthy":
                break
            time.sleep(1)
        if state != "healthy":
            latest_health = json.loads(run(["docker", "inspect", cid]))[0]["State"]["Health"]
            result["docker_health_failure"] = {
                "status": latest_health["Status"],
                "checks": [
                    {
                        "exit_code": check["ExitCode"],
                        "timed_out": "exceeded timeout" in check["Output"],
                    }
                    for check in latest_health.get("Log", [])
                ],
            }
        assert state == "healthy"
        result["docker_health"] = state
        result["runtime_uid_gid"] = {"uid": binding["uid"], "gid": binding["gid"]}
        assert all(
            (path.stat().st_uid, path.stat().st_gid) == (binding["uid"], binding["gid"])
            for path in (
                config,
                args.root / "var/lib/samuel",
                args.root / "var/log/samuel",
                args.root / "srv/samuel/backups",
                args.root / "srv/samuel/workspaces",
            )
        )
        result["ownership_from_image"] = "PASS"
        result["status"] = "PASS"
        return 0
    finally:
        command(compose + ["down", "--timeout", "10"], check=False)
        result["completed_at"] = datetime.now(timezone.utc).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
