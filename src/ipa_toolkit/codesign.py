"""
对 macOS `/usr/bin/codesign` 的轻量封装。

将签名相关细节收敛在此模块，便于上层流程保持清晰并易于测试。
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import tempfile
from typing import Any


def _run(
    cmd: list[str], *, check: bool = True, cwd: str | None = None
) -> subprocess.CompletedProcess[bytes]:
    """执行系统命令并返回 `subprocess` 结果对象。"""
    return subprocess.run(cmd, capture_output=True, check=check, cwd=cwd)


def remove_signature(path: str) -> None:
    """移除目标文件或应用包的现有签名（失败不抛错）。"""
    _run(["/usr/bin/codesign", "--remove-signature", path], check=False)


def sign(path: str, identity: str, entitlements_path: str | None = None) -> None:
    """使用给定证书与可选签名权限（`entitlements`）对目标签名。"""
    # `--timestamp=none` 可避免访问 Apple 时间戳服务，适合本地重签名场景。
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
    """对主应用包执行严格签名校验，失败则抛出异常。"""
    p = _run(["/usr/bin/codesign", "--verify", "--deep", "--strict", app_path], check=False)
    if p.returncode != 0:
        raise RuntimeError(f"codesign verify failed:\n{p.stderr.decode(errors='replace')}")


def extract_entitlements(target_path: str) -> dict[str, Any] | None:
    """从现有签名提取签名权限（`entitlements`），失败返回 `None`。"""
    # `codesign -d --entitlements :-` 会把 XML plist 输出到 stdout。
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
    """将签名权限字典写入临时 plist 并返回文件路径。"""
    data = plistlib.dumps(entitlements, fmt=plistlib.FMT_XML, sort_keys=False)
    fd, path = tempfile.mkstemp(prefix="ents_", suffix=".plist")
    os.close(fd)
    with open(path, "wb") as f:
        f.write(data)
    return path
