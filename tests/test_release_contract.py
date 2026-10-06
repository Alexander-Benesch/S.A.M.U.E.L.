from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_ci_binds_required_check_to_minimum_and_current_python() -> None:
    workflow = (ROOT / ".gitea" / "workflows" / "ci.yml").read_text()

    assert 'tags: ["v*"]' in workflow
    assert 'python-version: ["3.10.21", "3.14.7"]' in workflow
    assert workflow.count('python-version: "3.12.14"') == 2
    assert 'python-version: ["3.10", "3.14"]' not in workflow
    assert 'python-version: "3.12"' not in workflow
    assert "lint-and-test:\n    needs: python-compatibility" in workflow
    assert "release-gate:" in workflow
    assert "--mode post-tag" in workflow
    assert "--restore-remote-tag" in workflow
    assert "--commit-ref origin/main" in workflow
    assert "python tools/container_release.py check" in workflow


def test_ci_binds_runner_contract_and_external_actions() -> None:
    workflow = (ROOT / ".gitea" / "workflows" / "ci.yml").read_text()

    assert workflow.count("runs-on: public-runner-example") == 3
    assert workflow.count("timeout-minutes: 20") == 2
    assert workflow.count("timeout-minutes: 30") == 1
    assert workflow.count("fetch-depth: 0") == 3
    assert 'GIT_HTTP_LOW_SPEED_LIMIT: "1024"' in workflow
    assert 'GIT_HTTP_LOW_SPEED_TIME: "30"' in workflow
    assert 'python -m pip install -e ".[dev,ci,github]"' in workflow
    assert workflow.count("Verify image-baked Python") == 3
    assert workflow.count("test ! -S /var/run/docker.sock") == 3
    assert workflow.count('test -f "$cached_root/x64.complete"') == 3
    assert workflow.count('python -m venv "$RUNNER_TEMP/samuel-venv"') == 3
    assert workflow.count("/opt/hostedtoolcache/pip/pip-26.2.1-py3-none-any.whl") == 3
    assert workflow.count('= "26.2.1"') == 3
    assert workflow.count('echo "$RUNNER_TEMP/samuel-venv/bin" >> "$GITHUB_PATH"') == 3
    assert "runs-on: ubuntu-latest" not in workflow
    assert workflow.count("actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4") == 3
    assert workflow.count("actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5") == 3
    assert "actions/checkout@v4" not in workflow
    assert "actions/setup-python@v5" not in workflow


def test_ci_python_job_image_is_exact_immutable_and_socketless() -> None:
    operations = (ROOT / "docs" / "CI_RUNNER_OPERATIONS.md").read_text()
    image_build = (ROOT / "tools" / "build_ci_runner_image.sh").read_text()

    base_digest = "e77e2b1ebba51adb1c59d8eb185bc54e397b7e22442756aa7ea0e7b841fd2906"
    image_id = "0000000000000000000000000000000000000000000000000000000000000001"
    assert f"gitea/runner-images@sha256:{base_digest}" in operations
    assert f"public-runner-example:docker://sha256:{image_id}" in operations
    assert 'docker_host: "-"' in operations
    assert 'options: ""' in operations
    assert "tool_cache_mode: none" in operations
    assert "valid_volumes: []" in operations
    assert "Runner-Modus `shared`" in operations

    assert f"gitea/runner-images@sha256:{base_digest}" in image_build
    assert 'target_image="samuel/ci-python:20260827-3"' in image_build
    assert "docker build --pull=false --no-cache" in image_build
    assert 'docker image inspect "$target_image"' in image_build
    assert "base_platform" in image_build
    assert 'test ! -e "$version_root"' in image_build
    assert "test ! -S /var/run/docker.sock" in image_build
    assert "test ! -e /opt/hostedtoolcache/container-local-write-test" in image_build
    assert "pip-26.2.1-py3-none-any.whl" in image_build
    assert "71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e" in image_build
    assert "--no-index" in image_build
    for version, release, digest in (
        (
            "3.10.21",
            "3.10.21-31661269155",
            "3ae6d012a8c2cb41bf7a2957a99f1d6d329a264a727053e71edb76b1cfda6f52",
        ),
        (
            "3.12.14",
            "3.12.14-31661455385",
            "5a03168292516f6dd6dcf630f4bf5369b108abd7c699a7e1db37f1e622257fff",
        ),
        (
            "3.14.7",
            "3.14.7-31064857500",
            "76d5ddab6d2dd89a39c06220f6efeda486a48ed481eae97bfc596c74ac3623db",
        ),
    ):
        assert version in image_build
        assert release in image_build
        assert digest in image_build


def test_docker_context_excludes_secrets_and_carries_oci_identity() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    dockerignore = (ROOT / ".dockerignore").read_text().splitlines()
    compose = (ROOT / "docker-compose.yml").read_text()

    assert "COPY . ." not in dockerfile
    assert "org.opencontainers.image.version" in dockerfile
    assert "org.opencontainers.image.revision" in dockerfile
    assert 'ENV SAMUEL_BUILD_REVISION="${SAMUEL_REVISION}"' in dockerfile
    assert dockerignore[0] == "**"
    assert set(dockerignore[1:]) == {
        "!pyproject.toml",
        "!LICENSE",
        "!requirements-container.lock",
        "!requirements-container-build.lock",
        "!samuel/",
        "!samuel/**",
        "!config/",
        "!config/*.json",
        "!config/llm/",
        "!config/llm/*.json",
        "!config/workflows/",
        "!config/workflows/*.json",
        "config/license.json",
        "config/license.local.json",
    }
    for build_arg in ("SAMUEL_VERSION", "SAMUEL_REVISION", "SAMUEL_SOURCE_URL"):
        assert build_arg in compose
    assert "python:3.10-slim@sha256:" in dockerfile
    assert dockerfile.count("--require-hashes") == 2
    assert 'pip install --no-cache-dir ".[dashboard,llm,github,tree-sitter]"' not in dockerfile
    assert 'ENTRYPOINT ["samuel"]' in dockerfile
    assert "python -m samuel" not in dockerfile
    for variable in (
        "SAMUEL_IMAGE",
        "SAMUEL_ENV_FILE",
        "SAMUEL_CONFIG_DIR",
        "SAMUEL_DATA_DIR",
        "SAMUEL_DASHBOARD_BIND",
        "SAMUEL_DASHBOARD_PORT",
    ):
        assert variable in compose
    assert "/app/.env" not in compose
    assert 'command: ["dashboard", "--configuration-mode", "production"]' in compose
    setup_compose = (ROOT / "docker-compose.setup.yml").read_text()
    assert "${SAMUEL_ENV_FILE:-.env}:/app/.env:rw" in setup_compose
    assert "${SAMUEL_CONFIG_DIR:-./config}:/app/config:rw" in setup_compose
    assert '"--configuration-mode", "setup"' in setup_compose
    release_tool = (ROOT / "tools" / "container_release.py").read_text()
    assert '"--env-file"' in release_tool
    assert "compose_variables.write_text" in release_tool


def test_release_docs_define_abort_manual_fallback_and_container_contract() -> None:
    policy = (ROOT / "docs" / "VERSIONING.md").read_text()
    technical = (ROOT / "docs" / "README_technical.md").read_text()
    cli = (ROOT / "samuel" / "cli.py").read_text()

    for marker in (
        "tools/release_gate.py",
        "release-manifest.json",
        "Abbruchpunkt",
        "Gitea-Weboberfläche",
        "kein** Container-Image",
        "Python-3.10-/3.14",
        "SETUPTOOLS_SCM_PRETEND_VERSION_FOR_SAMUEL",
    ):
        assert marker in policy
    for marker in (
        "tools/container_release.py check",
        "Manifest-Schema 2",
        "keine Gitea-Abhängigkeit",
        "CONTAINER_RELEASE_OPERATIONS.md",
    ):
        assert marker in technical
    assert "samuel changelog --out CHANGELOG.md" not in cli


def test_current_release_surfaces_share_support_and_update_boundary() -> None:
    readme = (ROOT / "README.md").read_text()
    security = (ROOT / "SECURITY.md").read_text()
    install = (ROOT / "docs" / "INSTALL.md").read_text()
    versioning = (ROOT / "docs" / "VERSIONING.md").read_text()
    container_operations = (ROOT / "docs" / "CONTAINER_RELEASE_OPERATIONS.md").read_text()

    supported = re.findall(r"\| `([^`]+)` \| Latest supported alpha;", security)
    assert supported == ["2.0.0a15"]
    release_tag = f"v{supported[0]}"

    published = re.findall(r"\| `([^`]+)` \| Latest published alpha candidate;", security)
    assert published == ["2.0.0a25"]
    assert published[0] != supported[0]

    for surface in (readme, install, versioning, container_operations):
        assert release_tag in surface
    assert f"git checkout {release_tag}" in readme
    assert install.count(f"git checkout {release_tag}") == 2
    assert "#706" in install
    assert "kein qualifizierter Kundenupdatevertrag" in install
    assert "git pull\nsource .venv/bin/activate" in install
    assert "vollständige D0-PASS ist jedoch\n> nicht bestätigt" in readme
    assert "erhaltene a15-D0-Teilevidence" in readme
    assert "jüngste\n> veröffentlichte Alpha-Kandidat" in readme
    normalized_versioning = " ".join(versioning.split())
    assert "nicht durch einen Tag oder eine Main-CI selbst zum Release" in normalized_versioning
    assert "| `v2.0.0a15` | grün | Prerelease #29 | ja | ja | **partial** |" in versioning
    assert "| `v2.0.0a24` | grün | Prerelease #38 | ja | ja | **incomplete** |" in versioning
    assert "| `v2.0.0a25` | grün | Prerelease #39 | ja | ja | nein |" in versioning
