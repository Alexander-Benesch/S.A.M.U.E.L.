"""Tests fuer den Installer-Kern (.env-Merge + Doctor-Report)."""

from __future__ import annotations

from pathlib import Path

import pytest

from samuel.slices.setup.env_io import (
    GITEA_REQUIRED_STATUS_CONTEXT,
    build_doctor_report,
    gitea_release_policy_deviations,
    merge_env,
    parse_env,
)


def _protected_main_rules() -> dict:
    return {
        "enable_push": False,
        "enable_push_whitelist": False,
        "push_whitelist_usernames": [],
        "push_whitelist_teams": [],
        "push_whitelist_deploy_keys": False,
        "enable_force_push": False,
        "enable_force_push_allowlist": False,
        "force_push_allowlist_usernames": [],
        "force_push_allowlist_teams": [],
        "force_push_allowlist_deploy_keys": False,
        "enable_status_check": True,
        "block_admin_merge_override": True,
        "status_check_contexts": [GITEA_REQUIRED_STATUS_CONTEXT],
    }


class TestParseEnv:
    def test_parses_and_strips_quotes(self):
        out = parse_env("A=1\n# comment\nB=\"two\"\nC='three'\n\nbad line\n")
        assert out == {"A": "1", "B": "two", "C": "three"}

    def test_decodes_shell_safe_values(self):
        value = "token with $ and ' quote"
        assert parse_env(merge_env("", {"TOKEN": value}))["TOKEN"] == value


class TestMergeEnv:
    def test_updates_existing_preserves_comments(self):
        existing = "# header\nSCM_URL=old\nKEEP=yes\n"
        out = merge_env(existing, {"SCM_URL": "new"})
        assert "# header" in out
        assert "SCM_URL=new" in out
        assert "KEEP=yes" in out
        assert "SCM_URL=old" not in out

    def test_appends_new_keys(self):
        out = merge_env("A=1\n", {"B": "2"})
        assert "A=1" in out and "B=2" in out

    def test_empty_existing(self):
        out = merge_env("", {"X": "1"})
        assert out.strip() == "X=1"

    def test_quotes_values_that_shell_would_expand(self):
        out = merge_env("", {"TOKEN": "a$b c"})
        assert out == "TOKEN='a$b c'\n"


class TestDoctorReport:
    def _get(self, d):
        return lambda k: d.get(k)

    def test_scm_missing_is_fail(self, tmp_path: Path):
        checks = build_doctor_report(self._get({}), tmp_path)
        scm = [c for c in checks if c["name"] == "SCM-Konfiguration"][0]
        assert scm["status"] == "fail"

    def test_scm_present_ok(self, tmp_path: Path):
        env = {"SCM_URL": "u", "SCM_TOKEN": "t", "SCM_REPO": "o/r"}
        checks = build_doctor_report(self._get(env), tmp_path)
        scm = [c for c in checks if c["name"] == "SCM-Konfiguration"][0]
        assert scm["status"] == "ok"

    def test_scm_probe_fail(self, tmp_path: Path):
        checks = build_doctor_report(
            self._get({"SCM_URL": "u", "SCM_TOKEN": "t", "SCM_REPO": "o/r"}),
            tmp_path,
            scm_probe={"ok": False, "detail": "401"},
        )
        conn = [c for c in checks if c["name"] == "SCM-Verbindung"][0]
        assert conn["status"] == "fail" and "401" in conn["detail"]

    def test_branch_protection_denied_read_blocks_release_without_role_inference(
        self, tmp_path: Path
    ):
        checks = build_doctor_report(
            self._get({"SCM_URL": "u", "SCM_TOKEN": "t", "SCM_REPO": "o/r"}),
            tmp_path,
            scm_probe={
                "ok": True,
                "detail": "Repo o/r erreichbar",
                "branch_protection": {
                    "access": "restricted",
                    "detail": "Branchschutz-Read abgewiesen (HTTP 403); Mindestrecht unbekannt",
                },
            },
        )

        connection = next(c for c in checks if c["name"] == "SCM-Verbindung")
        protection = next(c for c in checks if c["name"] == "Branch-Protection (Release)")
        assert connection["status"] == "ok"
        assert protection["status"] == "fail"
        assert "keine Freigabe" in protection["fix"]
        assert "Admin" not in protection["fix"]
        assert "Operator" in protection["fix"]

    def test_branch_protection_matching_policy_is_ok(self, tmp_path: Path):
        checks = build_doctor_report(
            self._get({"SCM_URL": "u", "SCM_TOKEN": "t", "SCM_REPO": "o/r"}),
            tmp_path,
            scm_probe={
                "ok": True,
                "detail": "Repo o/r erreichbar",
                "branch_protection": {
                    "access": "ok",
                    "configured": True,
                    "branch": "main",
                    "rules": _protected_main_rules(),
                },
            },
        )

        protection = next(c for c in checks if c["name"] == "Branch-Protection (Release)")
        assert protection["status"] == "ok"
        assert "exakter Required Check" in protection["detail"]

        expected = next(c for c in checks if c["name"] == "SCM Required Check (Soll)")
        assert expected["status"] == "ok"
        assert GITEA_REQUIRED_STATUS_CONTEXT in expected["detail"]
        assert "ausgelieferter Default" in expected["detail"]

    def test_branch_protection_uses_configured_required_context(self, tmp_path: Path):
        required_context = "CI / demo-tests (pull_request)"
        rules = _protected_main_rules()
        rules["status_check_contexts"] = [required_context]
        checks = build_doctor_report(
            self._get(
                {
                    "SCM_PROVIDER": "gitea",
                    "SCM_URL": "u",
                    "SCM_TOKEN": "t",
                    "SCM_REPO": "o/r",
                    "SCM_REQUIRED_STATUS_CONTEXT": required_context,
                }
            ),
            tmp_path,
            scm_probe={
                "ok": True,
                "branch_protection": {
                    "access": "ok",
                    "configured": True,
                    "branch": "main",
                    "rules": rules,
                },
            },
        )

        expected = next(c for c in checks if c["name"] == "SCM Required Check (Soll)")
        protection = next(c for c in checks if c["name"] == "Branch-Protection (Release)")
        assert expected["status"] == "ok"
        assert "SCM_REQUIRED_STATUS_CONTEXT" in expected["detail"]
        assert required_context in protection["detail"]
        assert protection["status"] == "ok"

    def test_branch_protection_rejects_context_different_from_configured_value(
        self, tmp_path: Path
    ) -> None:
        required_context = "CI / demo-tests (pull_request)"
        checks = build_doctor_report(
            self._get(
                {
                    "SCM_PROVIDER": "gitea",
                    "SCM_URL": "u",
                    "SCM_TOKEN": "t",
                    "SCM_REPO": "o/r",
                    "SCM_REQUIRED_STATUS_CONTEXT": required_context,
                }
            ),
            tmp_path,
            scm_probe={
                "ok": True,
                "branch_protection": {
                    "access": "ok",
                    "configured": True,
                    "branch": "main",
                    "rules": _protected_main_rules(),
                },
            },
        )

        protection = next(c for c in checks if c["name"] == "Branch-Protection (Release)")
        assert protection["status"] == "fail"
        assert required_context in protection["detail"]

    def test_empty_configured_required_context_blocks(self, tmp_path: Path):
        rules = _protected_main_rules()
        checks = build_doctor_report(
            self._get(
                {
                    "SCM_PROVIDER": "gitea",
                    "SCM_URL": "u",
                    "SCM_TOKEN": "t",
                    "SCM_REPO": "o/r",
                    "SCM_REQUIRED_STATUS_CONTEXT": " ",
                }
            ),
            tmp_path,
            scm_probe={
                "ok": True,
                "branch_protection": {
                    "access": "ok",
                    "configured": True,
                    "branch": "main",
                    "rules": rules,
                },
            },
        )

        expected = next(c for c in checks if c["name"] == "SCM Required Check (Soll)")
        protection = next(c for c in checks if c["name"] == "Branch-Protection (Release)")
        assert expected["status"] == "fail"
        assert protection["status"] == "fail"

    def test_branch_protection_missing_rule_blocks_release(self, tmp_path: Path):
        checks = build_doctor_report(
            self._get({"SCM_URL": "u", "SCM_TOKEN": "t", "SCM_REPO": "o/r"}),
            tmp_path,
            scm_probe={
                "ok": True,
                "branch_protection": {
                    "access": "ok",
                    "configured": False,
                    "branch": "main",
                    "detail": "Keine Regel fuer main konfiguriert",
                },
            },
        )

        protection = next(c for c in checks if c["name"] == "Branch-Protection (Release)")
        assert protection["status"] == "fail"
        assert "Keine Regel" in protection["detail"]

    def test_missing_probe_result_blocks_release(self, tmp_path: Path):
        checks = build_doctor_report(
            self._get({"SCM_URL": "u", "SCM_TOKEN": "t", "SCM_REPO": "o/r"}),
            tmp_path,
            scm_probe={"ok": True, "detail": "Repo o/r erreichbar"},
        )

        protection = next(c for c in checks if c["name"] == "Branch-Protection (Release)")
        assert protection["status"] == "fail"
        assert "kein auswertbarer" in protection["detail"]

    def test_branch_protection_deviation_blocks_release(self, tmp_path: Path):
        rules = _protected_main_rules()
        rules["enable_push"] = True
        rules["block_admin_merge_override"] = False
        checks = build_doctor_report(
            self._get({"SCM_URL": "u", "SCM_TOKEN": "t", "SCM_REPO": "o/r"}),
            tmp_path,
            scm_probe={
                "ok": True,
                "branch_protection": {
                    "access": "ok",
                    "configured": True,
                    "branch": "main",
                    "rules": rules,
                },
            },
        )

        protection = next(c for c in checks if c["name"] == "Branch-Protection (Release)")
        assert protection["status"] == "fail"
        assert "enable_push muss false" in protection["detail"]
        assert "block_admin_merge_override muss true" in protection["detail"]

    def test_github_does_not_apply_gitea_release_policy(self, tmp_path: Path):
        checks = build_doctor_report(
            self._get(
                {
                    "SCM_PROVIDER": "github",
                    "SCM_URL": "u",
                    "SCM_TOKEN": "t",
                    "SCM_REPO": "o/r",
                }
            ),
            tmp_path,
            scm_probe={"ok": True, "detail": "Repo o/r erreichbar"},
        )

        protection = next(c for c in checks if c["name"] == "Branch-Protection (Release)")
        assert protection["status"] == "fail"
        assert "kein auswertbarer" in protection["detail"]

    def test_llm_missing_is_warn(self, tmp_path: Path):
        checks = build_doctor_report(self._get({}), tmp_path)
        llm = [c for c in checks if c["name"] == "LLM-Provider"][0]
        assert llm["status"] == "warn"

    def test_llm_present_ok(self, tmp_path: Path):
        checks = build_doctor_report(self._get({"DEEPSEEK_API_KEY": "x"}), tmp_path)
        llm = [c for c in checks if c["name"] == "LLM-Provider"][0]
        assert llm["status"] == "ok"

    def test_security_warns_without_keys(self, tmp_path: Path):
        checks = build_doctor_report(self._get({}), tmp_path)
        names = {c["name"]: c["status"] for c in checks}
        assert names["Dashboard-Auth (SAMUEL_API_KEY)"] == "warn"
        assert names["Webhook-Signaturschlüssel (SLICE_HMAC_KEY)"] == "warn"

    def test_directories_check(self, tmp_path: Path):
        (tmp_path / "config").mkdir()
        checks = build_doctor_report(self._get({}), tmp_path / "config")
        cfg = [c for c in checks if c["name"] == "Verzeichnis config"][0]
        assert cfg["status"] == "ok"

    def test_test_runner_reports_explicit_unittest_policy(self, tmp_path: Path):
        import json
        import sys

        config = tmp_path / "config"
        project = tmp_path / "project"
        config.mkdir()
        project.mkdir()
        (config / "eval.json").write_text(
            json.dumps(
                {
                    "test_policy_version": "doctor-runner.v1",
                    "test_cmd": f"{sys.executable} -m unittest {{test}}",
                }
            )
        )

        checks = build_doctor_report(
            self._get({"PROJECT_ROOT": str(project)}),
            config,
        )

        runner = next(c for c in checks if c["name"] == "TEST-Runner (Planning/Gate 11)")
        assert runner["status"] == "ok"
        assert "unittest" in runner["detail"]
        assert "gepunkteter" in runner["detail"]
        assert "doctor-runner.v1" in runner["detail"]

    def test_test_runner_missing_policy_and_marker_fails(self, tmp_path: Path):
        config = tmp_path / "config"
        project = tmp_path / "project"
        config.mkdir()
        project.mkdir()

        checks = build_doctor_report(
            self._get({"PROJECT_ROOT": str(project)}),
            config,
        )

        runner = next(c for c in checks if c["name"] == "TEST-Runner (Planning/Gate 11)")
        assert runner["status"] == "fail"
        assert "no test runner configured" in runner["detail"]
        assert "test_cmd" in runner["fix"]

    def test_test_runner_missing_binary_fails_without_command_disclosure(self, tmp_path: Path):
        import json

        config = tmp_path / "config"
        project = tmp_path / "project"
        config.mkdir()
        project.mkdir()
        (config / "eval.json").write_text(
            json.dumps(
                {
                    "test_cmd": "definitely-missing-samuel-runner --token hidden {test}",
                }
            )
        )

        checks = build_doctor_report(
            self._get({"PROJECT_ROOT": str(project)}),
            config,
        )

        runner = next(c for c in checks if c["name"] == "TEST-Runner (Planning/Gate 11)")
        assert runner["status"] == "fail"
        assert "definitely-missing-samuel-runner" in runner["detail"]
        assert "hidden" not in str(runner)


class TestGiteaReleasePolicy:
    def test_exact_policy_has_no_deviation(self):
        assert gitea_release_policy_deviations(_protected_main_rules()) == []

    def test_missing_fields_fail_closed(self):
        deviations = gitea_release_policy_deviations({})
        assert "enable_push muss false sein" in deviations
        assert "push_whitelist_usernames muss leer sein" in deviations
        assert "force_push_allowlist_deploy_keys muss false sein" in deviations
        assert any("status_check_contexts muss exakt" in item for item in deviations)

    def test_dormant_allowlist_entries_are_rejected(self):
        rules = _protected_main_rules()
        rules["push_whitelist_usernames"] = ["admin"]
        rules["force_push_allowlist_deploy_keys"] = True

        deviations = gitea_release_policy_deviations(rules)

        assert "push_whitelist_usernames muss leer sein" in deviations
        assert "force_push_allowlist_deploy_keys muss false sein" in deviations

    def test_wrong_or_additional_context_is_rejected(self):
        rules = _protected_main_rules()
        rules["status_check_contexts"] = [GITEA_REQUIRED_STATUS_CONTEXT, "other/check"]
        assert any(
            "status_check_contexts muss exakt" in item
            for item in gitea_release_policy_deviations(rules)
        )


@pytest.mark.parametrize("present", [False, True])
def test_doctor_webhook_key_presence_does_not_claim_signature_or_native_delivery(tmp_path, present):
    value = "fixture-signing-key"
    checks = build_doctor_report(
        lambda key: value if present and key == "SLICE_HMAC_KEY" else None, tmp_path
    )
    signing = next(c for c in checks if "SLICE_HMAC_KEY" in c["name"])
    assert "Signaturschlüssel" in signing["name"]
    assert signing["status"] == ("ok" if present else "warn")
    assert "native SCM-Delivery" in signing["detail"]
    if present:
        assert "nicht geprüft" in signing["detail"]
    assert value not in str(checks)
