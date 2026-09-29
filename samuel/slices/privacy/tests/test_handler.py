from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from samuel.core.bus import Bus
from samuel.slices.privacy.handler import (
    PrivacyHandler,
    PromptSanitizer,
    TransferWarning,
    load_configured_provider_names,
)


class TestPromptSanitizer:
    def test_scrub_email(self):
        s = PromptSanitizer()
        text, redactions = s.sanitize("Contact john@example.com for details")

        assert "john@example.com" not in text
        assert "[REDACTED:email]" in text
        assert len(redactions) == 1
        assert redactions[0]["type"] == "email"
        assert len(redactions[0]["hash"]) == 12

    def test_scrub_ip_address(self):
        s = PromptSanitizer()
        text, redactions = s.sanitize("Server at 192.0.2.25 is down")

        assert "192.0.2.25" not in text
        assert "[REDACTED:ip_address]" in text

    def test_scrub_multiple_pii(self):
        s = PromptSanitizer()
        text, redactions = s.sanitize("User test@mail.com from 192.0.2.26 called +49 170 1234567")

        assert "test@mail.com" not in text
        assert "192.0.2.26" not in text
        assert len(redactions) >= 2

    def test_no_pii_returns_unchanged(self):
        s = PromptSanitizer()
        text, redactions = s.sanitize("This is a normal prompt without PII")

        assert text == "This is a normal prompt without PII"
        assert redactions == []

    def test_disabled_returns_unchanged(self):
        s = PromptSanitizer({"enabled": False})
        text, redactions = s.sanitize("Secret: john@example.com")

        assert "john@example.com" in text
        assert redactions == []

    def test_selective_patterns(self):
        s = PromptSanitizer({"patterns": ["email"]})
        text, redactions = s.sanitize("john@example.com at 192.0.2.27")

        assert "john@example.com" not in text
        assert "192.0.2.27" in text

    def test_empty_string(self):
        s = PromptSanitizer()
        text, redactions = s.sanitize("")
        assert text == ""
        assert redactions == []

    def test_credit_card(self):
        s = PromptSanitizer()
        text, redactions = s.sanitize("Card: 4111-1111-1111-1111")
        assert "4111" not in text
        assert "[REDACTED:credit_card]" in text


class TestTransferWarning:
    def test_local_provider_allowed(self):
        tw = TransferWarning(
            {
                "allowed_regions": ["EU"],
                "provider_locations": {"ollama": "local"},
            }
        )

        result = tw.check_provider("ollama")
        assert result["allowed"] is True
        assert result["warning"] is None

    def test_eu_provider_allowed(self):
        tw = TransferWarning(
            {
                "allowed_regions": ["EU", "EEA"],
                "provider_locations": {"mistral": "EU"},
            }
        )

        result = tw.check_provider("mistral")
        assert result["allowed"] is True

    def test_us_provider_warning(self):
        tw = TransferWarning(
            {
                "allowed_regions": ["EU"],
                "provider_locations": {"anthropic": "US"},
            }
        )

        result = tw.check_provider("anthropic")
        assert result["allowed"] is False
        assert "Drittland-Transfer" in result["warning"]
        assert "Art. 44-49" in result["warning"]

    def test_cn_provider_warning(self):
        tw = TransferWarning(
            {
                "allowed_regions": ["EU"],
                "provider_locations": {"deepseek": "CN"},
            }
        )

        result = tw.check_provider("deepseek")
        assert result["allowed"] is False

    def test_check_all_providers(self):
        tw = TransferWarning(
            {
                "allowed_regions": ["EU"],
                "provider_locations": {"ollama": "local", "anthropic": "US"},
            }
        )

        results = tw.check_all_providers()
        assert len(results) == 2
        allowed = [r for r in results if r["allowed"]]
        warned = [r for r in results if not r["allowed"]]
        assert len(allowed) == 1
        assert len(warned) == 1

    def test_unknown_provider(self):
        tw = TransferWarning(
            {
                "allowed_regions": ["EU"],
                "provider_locations": {},
            }
        )

        result = tw.check_provider("unknown_provider")
        assert result["location"] == "unknown"
        assert result["allowed"] is False

    def test_configured_provider_without_location_is_warned(self):
        tw = TransferWarning(
            {
                "allowed_regions": ["EU"],
                "provider_locations": {"ollama": "local"},
            },
            providers=["ollama", "missing-provider"],
        )

        results = {result["provider"]: result for result in tw.check_all_providers()}
        assert results["missing-provider"]["location"] == "unknown"
        assert results["missing-provider"]["allowed"] is False
        assert results["missing-provider"]["warning"] is not None

    @pytest.mark.parametrize("flag", [True, None])
    def test_transfer_warning_enabled_or_omitted_warns(self, flag):
        config: dict[str, Any] = {
            "allowed_regions": ["EU"],
            "provider_locations": {"openai": "US"},
        }
        if flag is not None:
            config["transfer_warning"] = flag

        result = TransferWarning(config).check_provider("openai")

        assert result["allowed"] is False
        assert result["warning"] is not None

    def test_transfer_warning_false_suppresses_message_not_classification(self):
        result = TransferWarning(
            {
                "allowed_regions": ["EU"],
                "provider_locations": {"openai": "US"},
                "transfer_warning": False,
            }
        ).check_provider("openai")

        assert result["location"] == "US"
        assert result["allowed"] is False
        assert result["warning"] is None

    def test_shipped_location_keys_match_provider_catalogue(self):
        project_root = Path(__file__).resolve().parents[4]
        provider_names = load_configured_provider_names(project_root / "config")
        privacy = json.loads((project_root / "config" / "privacy.json").read_text())
        assert set(privacy["provider_locations"]) == set(provider_names)
        assert "claude" in provider_names
        assert "anthropic" not in privacy["provider_locations"]

    def test_privacy_handler_uses_configured_provider_catalogue(self, tmp_path: Path):
        project_root = Path(__file__).resolve().parents[4]
        retention = json.loads((project_root / "config" / "privacy.json").read_text())["retention"]
        (tmp_path / "llm").mkdir()
        (tmp_path / "llm" / "providers.json").write_text(
            json.dumps({"providers": {"claude": {}, "new-provider": {}}})
        )
        (tmp_path / "privacy.json").write_text(
            json.dumps(
                {
                    "allowed_regions": ["EU"],
                    "provider_locations": {"claude": "US"},
                    "transfer_warning": True,
                    "retention": retention,
                }
            )
        )

        handler = PrivacyHandler(bus=Bus(), config_dir=tmp_path)
        results = {result["provider"]: result for result in handler.transfer.check_all_providers()}
        assert results["claude"]["location"] == "US"
        assert results["new-provider"]["location"] == "unknown"
        assert results["new-provider"]["warning"] is not None


class TestHandleDeleteUserData:
    def test_no_logs_dir(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        handler = PrivacyHandler(bus=Bus())
        result = handler.handle_delete_user_data("alice@example.com")

        assert result["status"] == "no_logs_dir"
        assert result["anonymized_entries"] == 0
        assert result["files_touched"] == []

    def test_empty_identifier(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        handler = PrivacyHandler(bus=Bus())
        result = handler.handle_delete_user_data("")

        assert result["status"] == "empty_identifier"
        assert result["anonymized_entries"] == 0

    def test_anonymizes_matching_entries(self, tmp_path: Path, monkeypatch):
        logs_dir = tmp_path / "data" / "logs"
        logs_dir.mkdir(parents=True)
        f1 = logs_dir / "audit_1.jsonl"
        f1.write_text(
            json.dumps({"event": "Foo", "payload": {"user": "alice@example.com"}})
            + "\n"
            + json.dumps({"event": "Bar", "payload": {"user": "bob@example.com"}})
            + "\n"
        )
        f2 = logs_dir / "audit_2.jsonl"
        f2.write_text(
            json.dumps({"event": "Baz", "payload": {"who": "alice@example.com asked"}}) + "\n"
        )
        monkeypatch.chdir(tmp_path)

        handler = PrivacyHandler(bus=Bus())
        result = handler.handle_delete_user_data("alice@example.com")

        assert result["status"] == "completed"
        assert result["anonymized_entries"] == 2
        assert sorted(result["files_touched"]) == ["audit_1.jsonl", "audit_2.jsonl"]
        assert "alice@example.com" not in f1.read_text()
        assert "alice@example.com" not in f2.read_text()
        assert "bob@example.com" in f1.read_text()
        assert "[ANONYMIZED:user:" in f1.read_text()

    def test_no_match_no_files_touched(self, tmp_path: Path, monkeypatch):
        logs_dir = tmp_path / "data" / "logs"
        logs_dir.mkdir(parents=True)
        f = logs_dir / "audit.jsonl"
        original = json.dumps({"event": "Foo", "payload": {"user": "carol@example.com"}}) + "\n"
        f.write_text(original)
        monkeypatch.chdir(tmp_path)

        handler = PrivacyHandler(bus=Bus())
        result = handler.handle_delete_user_data("alice@example.com")

        assert result["anonymized_entries"] == 0
        assert result["files_touched"] == []
        assert f.read_text() == original

    def test_skips_invalid_json_lines(self, tmp_path: Path, monkeypatch):
        logs_dir = tmp_path / "data" / "logs"
        logs_dir.mkdir(parents=True)
        f = logs_dir / "audit.jsonl"
        f.write_text(
            "not valid json\n" + json.dumps({"event": "Foo", "user": "alice@example.com"}) + "\n"
        )
        monkeypatch.chdir(tmp_path)

        handler = PrivacyHandler(bus=Bus())
        result = handler.handle_delete_user_data("alice@example.com")

        assert result["anonymized_entries"] == 1
        text = f.read_text()
        assert "not valid json" in text
        assert "alice@example.com" not in text
