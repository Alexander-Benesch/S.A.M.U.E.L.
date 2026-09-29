from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path


class WorkspaceRollbackError(RuntimeError):
    """Content-free signal that restoration after an exception also failed."""

    def __init__(self, *, trigger_reason: str, rollback: dict[str, str | int]) -> None:
        super().__init__("implementation workspace rollback failed")
        self.trigger_reason = trigger_reason
        self.rollback = rollback


@dataclass(frozen=True)
class _FileSnapshot:
    path: Path
    existed: bool
    content: bytes | None
    mode: int | None
    missing_directories: tuple[Path, ...]


class WorkspaceTransaction:
    """Restore only paths first touched by one implementation call.

    The transaction deliberately does not use Git reset, checkout, or stash:
    an operator's pre-existing content is the captured baseline and must not be
    replaced by a repository revision. Patch-target containment is a separate
    policy boundary tracked in #600.
    """

    def __init__(self) -> None:
        self._snapshots: dict[Path, _FileSnapshot] = {}
        self._order: list[Path] = []
        self._missing_directories: set[Path] = set()
        self._closed = False

    def capture(self, path: Path) -> None:
        if self._closed:
            raise RuntimeError("workspace transaction is already closed")

        target = path.resolve(strict=False)
        if target in self._snapshots:
            return

        missing_directories: list[Path] = []
        parent = target.parent
        while not parent.exists() and parent != parent.parent:
            missing_directories.append(parent)
            self._missing_directories.add(parent)
            parent = parent.parent

        if target.exists():
            if not target.is_file():
                raise IsADirectoryError(target)
            snapshot = _FileSnapshot(
                path=target,
                existed=True,
                content=target.read_bytes(),
                mode=stat.S_IMODE(target.stat().st_mode),
                missing_directories=tuple(missing_directories),
            )
        else:
            snapshot = _FileSnapshot(
                path=target,
                existed=False,
                content=None,
                mode=None,
                missing_directories=tuple(missing_directories),
            )

        self._snapshots[target] = snapshot
        self._order.append(target)

    def release_if_unchanged(self, path: Path) -> bool:
        """Drop a precautionary snapshot only when no mutation occurred."""

        if self._closed:
            raise RuntimeError("workspace transaction is already closed")
        target = path.resolve(strict=False)
        snapshot = self._snapshots.get(target)
        if snapshot is None:
            return False

        try:
            if snapshot.existed:
                unchanged = (
                    target.is_file()
                    and target.read_bytes() == snapshot.content
                    and stat.S_IMODE(target.stat().st_mode) == snapshot.mode
                )
            else:
                unchanged = not target.exists() and not target.is_symlink()
        except OSError:
            return False
        if not unchanged:
            return False

        self._snapshots.pop(target)
        self._order.remove(target)
        self._missing_directories = {
            directory
            for remaining in self._snapshots.values()
            for directory in remaining.missing_directories
        }
        return True

    def commit(self) -> None:
        self._closed = True
        self._snapshots.clear()
        self._order.clear()
        self._missing_directories.clear()

    def rollback(self) -> dict[str, str | int]:
        if self._closed or not self._order:
            self._closed = True
            return {
                "status": "not_needed",
                "files_restored": 0,
                "files_removed": 0,
                "directories_removed": 0,
                "failures": 0,
            }

        restored = 0
        removed = 0
        directories_removed = 0
        failures = 0

        for target in reversed(self._order):
            snapshot = self._snapshots[target]
            try:
                if snapshot.existed:
                    assert snapshot.content is not None
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(snapshot.content)
                    if snapshot.mode is not None:
                        target.chmod(snapshot.mode)
                    restored += 1
                elif target.exists() or target.is_symlink():
                    if target.is_dir() and not target.is_symlink():
                        raise IsADirectoryError(target)
                    target.unlink()
                    removed += 1
            except OSError:
                failures += 1

        for directory in sorted(
            self._missing_directories,
            key=lambda value: len(value.parts),
            reverse=True,
        ):
            try:
                if directory.exists():
                    directory.rmdir()
                    directories_removed += 1
            except OSError:
                failures += 1

        self._closed = True
        return {
            "status": "failed" if failures else "completed",
            "files_restored": restored,
            "files_removed": removed,
            "directories_removed": directories_removed,
            "failures": failures,
        }
