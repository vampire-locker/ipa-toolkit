from __future__ import annotations

"""
Thin wrappers around macOS `/usr/bin/codesign`.

We keep this module focused so higher-level logic in `ipa.py` can stay testable
and readable.
"""

import os
import plistlib
import subprocess
import tempfile
from typing import Any


def _run(cmd: list[str], *, check: bool = True, cwd: str | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check, cwd=cwd)


def remove_signature(path: str) -> None:
    _run(["/usr/bin/codesign", "--remove-signature", path], check=False)


def sign(path: str, identity: str, entitlements_path: str | None = None) -> None:
    # `--timestamp=none` avoids contacting Apple's timestamp server (common for
    # internal signing / re-signing workflows).
    cmd = ["/usr/bin/codesign", "-f", "-s", identity, "--timestamp=none"]
    if entitlements_path:
        cmd += ["--entitlements", entitlements_path]
    cmd.append(path)
    p = _run(cmd, check=False)
    if p.returncode != 0:
        raise RuntimeError(
            f"codesign failed: {path}\n{p.stderr.decode(errors='replace')}"
        )


def verify(app_path: str) -> None:
    p = _run(["/usr/bin/codesign", "--verify", "--deep", "--strict", app_path], check=False)
    if p.returncode != 0:
        raise RuntimeError(f"codesign verify failed:\n{p.stderr.decode(errors='replace')}")


def extract_entitlements(target_path: str) -> dict[str, Any] | None:
    # `codesign -d --entitlements :-` prints a plist (xml) to stdout.
    p = _run(["/usr/bin/codesign", "-d", "--entitlements", ":-", target_path], check=False)
    if p.returncode != 0 or not p.stdout:
        return None
    try:
        obj = plistlib.loads(p.stdout)
    except Exception:
        return None
    if isinstance(obj, dict):
        return obj
    return None


def write_entitlements(entitlements: dict[str, Any]) -> str:
    data = plistlib.dumps(entitlements, fmt=plistlib.FMT_XML, sort_keys=False)
    fd, path = tempfile.mkstemp(prefix="ents_", suffix=".plist")
    os.close(fd)
    with open(path, "wb") as f:
        f.write(data)
    return path
