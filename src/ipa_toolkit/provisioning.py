from __future__ import annotations

"""
Provisioning profile helpers.

`.mobileprovision` files are CMS-wrapped plists. We rely on macOS `security cms`
to decode them.
"""

import plistlib
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProvisioningProfile:
    raw: dict[str, Any]
    team_id: str
    entitlements: dict[str, Any]


def _run(cmd: list[str]) -> bytes:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr.decode(errors='replace')}")
    return p.stdout


def load_mobileprovision(path: str) -> ProvisioningProfile:
    # `security cms -D -i` outputs an XML plist.
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
