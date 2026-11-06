"""Workspace identities and failures shared across slices and adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

WorkspaceProfile = Literal["run", "verification"]
WorkspaceStatus = Literal["creating", "active", "terminal", "quarantined"]


class WorkspaceError(RuntimeError):
    """Content-bounded workspace failure safe for operator-facing output."""

    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


@dataclass(frozen=True)
class WorkspaceHandle:
    workspace_id: str
    profile: WorkspaceProfile
    repository_root: Path
    path: Path
    branch: str
    head_sha: str
    base_ref: str
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["repository_root"] = str(self.repository_root)
        payload["path"] = str(self.path)
        return payload


@dataclass(frozen=True)
class WorkspaceRecord:
    workspace_id: str
    profile: WorkspaceProfile
    repository_root: str
    path: str
    branch: str
    head_sha: str
    base_ref: str
    status: WorkspaceStatus
    reserved_bytes: int
    owner_pid: int
    created_at: str
    updated_at: str
    quarantine_until: str = ""
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
