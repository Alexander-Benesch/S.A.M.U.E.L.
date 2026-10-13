from unittest.mock import Mock

import pytest

from samuel.core.bus import Bus
from samuel.core.ports import IVersionControl
from samuel.slices.dashboard.handler import DashboardHandler


class UnreadableRule(RuntimeError):
    def __init__(self, status: int) -> None:
        super().__init__("synthetic-secret-in-provider-error")
        self.status = status


@pytest.mark.parametrize("status", [401, 403])
def test_rule_read_denial_does_not_infer_repository_admin(status: int) -> None:
    scm = Mock(spec=IVersionControl)
    scm.capabilities = {"branch_protection"}
    scm.get_branch_protection.side_effect = UnreadableRule(status)
    result = DashboardHandler(Bus(), scm=scm)._get_branch_protection_status()
    assert result["error"] == "permission_denied"
    assert result["http_status"] == status
    assert result["required_permission"] == "unknown"
    assert result["rules"] is None
    assert result["protected"] is False
    assert "synthetic-secret" not in str(result)
    scm.get_branch_protection.assert_called_once_with("main")


def test_rule_unknown_error_does_not_copy_exception_into_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    scm = Mock(spec=IVersionControl)
    scm.capabilities = {"branch_protection"}
    scm.get_branch_protection.side_effect = RuntimeError("synthetic-secret-in-provider-error")
    result = DashboardHandler(Bus(), scm=scm)._get_branch_protection_status()
    assert result["error"] == "request_failed"
    assert "required_permission" not in result
    assert "synthetic-secret" not in str(result)
    assert "synthetic-secret" not in caplog.text


def test_non_admin_readable_rule_is_reported_without_privilege_advice() -> None:
    scm = Mock(spec=IVersionControl)
    scm.capabilities = {"branch_protection"}
    scm.get_branch_protection.return_value = {"enable_status_check": True}
    result = DashboardHandler(Bus(), scm=scm)._get_branch_protection_status()
    assert result["protected"] is True
    assert "required_permission" not in result
    assert "error" not in result
