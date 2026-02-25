"""
签名描述文件（`mobileprovision`）解析辅助模块。

`.mobileprovision` 本质是 CMS 封装的 plist，这里通过 macOS `security cms` 解码。
"""

from __future__ import annotations

import plistlib
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProvisioningProfile:
    """描述已解析签名描述文件的关键信息。"""

    raw: dict[str, Any]
    team_id: str
    entitlements: dict[str, Any]


def _run(cmd: list[str]) -> bytes:
    """执行命令并返回 stdout，失败时抛出异常。"""
    p = subprocess.run(cmd, capture_output=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr.decode(errors='replace')}")
    return p.stdout


def load_mobileprovision(path: str) -> ProvisioningProfile:
    """解析 `.mobileprovision` 并提取团队标识（Team ID）与签名权限。"""
    # `security cms -D -i` 会输出 XML 格式的 plist。
    data = _run(["/usr/bin/security", "cms", "-D", "-i", path])
    raw = plistlib.loads(data)
    ents = raw.get("Entitlements", {}) if isinstance(raw, dict) else {}

    team_id = ""
    v = ents.get("com.apple.developer.team-identifier")
    if isinstance(v, str) and v:
        team_id = v
    if not team_id:
        app_id = ents.get("application-identifier")
        if isinstance(app_id, str) and "." in app_id:
            team_id = app_id.split(".", 1)[0]

    if not team_id:
        raise RuntimeError("Failed to extract team id from provisioning profile")

    if not isinstance(ents, dict):
        ents = {}
    return ProvisioningProfile(raw=raw, team_id=team_id, entitlements=ents)
