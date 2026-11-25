"""Installed Git askpass helper; credentials are read only from its environment."""

from __future__ import annotations

import os
import sys

USERNAME_ENV = "SAMUEL_GIT_ASKPASS_USERNAME"
SECRET_ENV = "SAMUEL_GIT_ASKPASS_SECRET"


def main() -> int:
    prompt = sys.argv[1] if len(sys.argv) == 2 else ""
    if "username" in prompt.lower():
        value = os.environ.get(USERNAME_ENV, "")
    elif "password" in prompt.lower():
        value = os.environ.get(SECRET_ENV, "")
    else:
        return 1
    if not value or "\n" in value or "\r" in value or "\0" in value:
        return 1
    sys.stdout.write(f"{value}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover - console-script boundary
    raise SystemExit(main())
