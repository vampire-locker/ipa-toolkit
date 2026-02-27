"""
签名描述文件（`mobileprovision`）解析辅助模块。

`.mobileprovision` 本质是 CMS 封装的 plist，这里通过 macOS `security cms` 解码。
"""

from __future__ import annotations

import hashlib
import plistlib
import re
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProvisioningProfile:
    """描述已解析签名描述文件的关键信息。"""

    raw: dict[str, Any]
    team_id: str
    entitlements: dict[str, Any]


_IDENTITY_LINE_RE = re.compile(r'^\s*\d+\)\s+([0-9A-Fa-f]{40})\s+"(.+)"\s*$')


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


def profile_certificate_sha1s(profile: ProvisioningProfile) -> list[str]:
    """从 profile 的 `DeveloperCertificates` 提取证书 SHA1（大写十六进制）。"""
    certs = profile.raw.get("DeveloperCertificates")
    if not isinstance(certs, list):
        return []

    out: list[str] = []
    seen: set[str] = set()
    for cert in certs:
        if not isinstance(cert, (bytes, bytearray)):
            continue
        fingerprint = hashlib.sha1(bytes(cert)).hexdigest().upper()
        if fingerprint not in seen:
            seen.add(fingerprint)
            out.append(fingerprint)
    return out


def list_codesigning_identities() -> list[tuple[str, str]]:
    """列出钥匙串中可用于 codesign 的身份 `(sha1, name)`。"""
    text = _run(["/usr/bin/security", "find-identity", "-v", "-p", "codesigning"]).decode(
        errors="replace"
    )
    out: list[tuple[str, str]] = []
    for line in text.splitlines():
        m = _IDENTITY_LINE_RE.match(line.strip())
        if not m:
            continue
        out.append((m.group(1).upper(), m.group(2)))
    return out


def resolve_sign_identity_from_profile(profile: ProvisioningProfile) -> str:
    """根据 profile 选择一个可用于 `codesign -s` 的身份值。"""
    cert_hashes = profile_certificate_sha1s(profile)
    if not cert_hashes:
        raise RuntimeError("Provisioning profile has no DeveloperCertificates")

    # 优先返回钥匙串中已存在的“名称”身份；找不到时回退为证书 SHA1。
    by_hash = {fingerprint: name for fingerprint, name in list_codesigning_identities()}
    for cert_hash in cert_hashes:
        name = by_hash.get(cert_hash)
        if name:
            return name
    return cert_hashes[0]
