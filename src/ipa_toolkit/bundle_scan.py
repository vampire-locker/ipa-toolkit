from __future__ import annotations

"""
Helpers for locating and mapping app bundles inside an unzipped IPA payload.
"""

import os

from .plist_edit import load_plist


def find_main_app(payload_path: str, main_app_name: str = "") -> str:
    apps: list[str] = []
    for name in sorted(os.listdir(payload_path)):
        p = os.path.join(payload_path, name)
        if os.path.isdir(p) and name.endswith(".app"):
            apps.append(p)

    if not apps:
        return ""

    if main_app_name:
        raw = os.path.basename(main_app_name.strip())
        target = raw if raw.endswith(".app") else f"{raw}.app"
        for app in apps:
            if os.path.basename(app) == target:
                return app
        found = ", ".join(os.path.basename(x) for x in apps)
        raise SystemExit(
            f"Error: main app not found: {target}. Available under Payload/: {found}"
        )

    if len(apps) == 1:
        return apps[0]

    appl_apps: list[str] = []
    for app in apps:
        info_path = os.path.join(app, "Info.plist")
        if not os.path.isfile(info_path):
            continue
        try:
            info = load_plist(info_path)
        except Exception:
            continue
        if isinstance(info, dict) and info.get("CFBundlePackageType") == "APPL":
            appl_apps.append(app)

    if len(appl_apps) == 1:
        return appl_apps[0]

    found = ", ".join(os.path.basename(x) for x in apps)
    raise SystemExit(
        "Error: multiple .app found under Payload/. "
        f"Please specify --main-app-name. Available: {found}"
    )


def find_bundles_under(app_path: str) -> list[str]:
    out: list[str] = [app_path]
    for root, dirs, _files in os.walk(app_path):
        for d in dirs:
            if d.endswith(".app") or d.endswith(".appex") or d.endswith(".xpc"):
                out.append(os.path.join(root, d))
    out.sort(key=lambda p: (0 if p == app_path else 1, len(p)))
    return out


def bundle_new_id_for(old_id: str, old_main_id: str, new_main_id: str) -> str:
    if not new_main_id:
        return old_id
    if old_id == old_main_id:
        return new_main_id
    if old_id.startswith(old_main_id + "."):
        return new_main_id + old_id[len(old_main_id):]
    return old_id
