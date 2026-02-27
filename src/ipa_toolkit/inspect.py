"""
IPA 只读信息查看模块。

用于在不解包重签、不修改文件的情况下，快速查看 IPA 关键元数据。
"""

from __future__ import annotations

import os
import plistlib
import zipfile
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BundleInfo:
    """单个 bundle 的关键信息。"""

    path: str
    name: str
    bundle_id: str
    package_type: str


@dataclass(frozen=True)
class IpaInfo:
    """IPA 关键信息快照。"""

    input_ipa: str
    main_app: BundleInfo
    display_name: str
    version: str
    build: str
    min_os_version: str
    url_schemes: list[str]
    has_embedded_profile: bool
    nested_bundles: list[BundleInfo]


def _plist_str(d: dict[str, Any], key: str) -> str:
    v = d.get(key)
    return v if isinstance(v, str) else ""


def _extract_bundle_infos(zf: zipfile.ZipFile) -> list[tuple[BundleInfo, dict[str, Any]]]:
    out: list[tuple[BundleInfo, dict[str, Any]]] = []
    names = set(zf.namelist())

    for name in sorted(names):
        if not name.startswith("Payload/") or not name.endswith("/Info.plist"):
            continue
        bundle_path = name[: -len("/Info.plist")]
        leaf = bundle_path.rsplit("/", 1)[-1]
        if not (leaf.endswith(".app") or leaf.endswith(".appex") or leaf.endswith(".xpc")):
            continue

        raw = zf.read(name)
        obj = plistlib.loads(raw)
        if not isinstance(obj, dict):
            continue

        info = BundleInfo(
            path=bundle_path,
            name=leaf,
            bundle_id=_plist_str(obj, "CFBundleIdentifier"),
            package_type=_plist_str(obj, "CFBundlePackageType"),
        )
        out.append((info, obj))
    return out


def _pick_main_app(
    bundle_infos: list[tuple[BundleInfo, dict[str, Any]]],
    *,
    main_app_name: str,
) -> tuple[BundleInfo, dict[str, Any]]:
    apps = [(info, obj) for info, obj in bundle_infos if info.name.endswith(".app")]
    top_apps = [(info, obj) for info, obj in apps if info.path.count("/") == 1]

    if not top_apps:
        raise SystemExit("Error: .app not found under Payload/.")

    if main_app_name:
        raw = os.path.basename(main_app_name.strip())
        target = raw if raw.endswith(".app") else f"{raw}.app"
        for info, obj in top_apps:
            if info.name == target:
                return info, obj
        found = ", ".join(sorted(info.name for info, _obj in top_apps))
        raise SystemExit(
            f"Error: main app not found: {target}. Available under Payload/: {found}"
        )

    if len(top_apps) == 1:
        return top_apps[0]

    appl_apps = [(info, obj) for info, obj in top_apps if info.package_type == "APPL"]
    if len(appl_apps) == 1:
        return appl_apps[0]

    found = ", ".join(sorted(info.name for info, _obj in top_apps))
    raise SystemExit(
        "Error: multiple .app found under Payload/. "
        f"Please specify --main-app-name. Available: {found}"
    )


def _collect_url_schemes(main_plist: dict[str, Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    url_types = main_plist.get("CFBundleURLTypes")
    if not isinstance(url_types, list):
        return out
    for item in url_types:
        if not isinstance(item, dict):
            continue
        schemes = item.get("CFBundleURLSchemes")
        if not isinstance(schemes, list):
            continue
        for scheme in schemes:
            if isinstance(scheme, str) and scheme and scheme not in seen:
                seen.add(scheme)
                out.append(scheme)
    return out


def inspect_ipa(input_ipa: str, *, main_app_name: str = "") -> IpaInfo:
    """读取 IPA 元数据并返回结构化结果。"""
    if not os.path.isfile(input_ipa):
        raise SystemExit(f"Error: ipa not found: {input_ipa}")

    with zipfile.ZipFile(input_ipa, "r") as zf:
        names = set(zf.namelist())
        if not any(n == "Payload/" or n.startswith("Payload/") for n in names):
            raise SystemExit("Error: Payload not found in ipa.")

        bundle_infos = _extract_bundle_infos(zf)
        main_info, main_plist = _pick_main_app(bundle_infos, main_app_name=main_app_name)

        main_prefix = main_info.path + "/"
        nested: list[BundleInfo] = []
        for info, _obj in bundle_infos:
            if info.path == main_info.path:
                continue
            if info.path.startswith(main_prefix):
                nested.append(info)
        nested.sort(key=lambda x: (len(x.path), x.path))

        has_profile = f"{main_info.path}/embedded.mobileprovision" in names
        display_name = _plist_str(main_plist, "CFBundleDisplayName") or _plist_str(
            main_plist, "CFBundleName"
        )

        return IpaInfo(
            input_ipa=input_ipa,
            main_app=main_info,
            display_name=display_name,
            version=_plist_str(main_plist, "CFBundleShortVersionString"),
            build=_plist_str(main_plist, "CFBundleVersion"),
            min_os_version=_plist_str(main_plist, "MinimumOSVersion"),
            url_schemes=_collect_url_schemes(main_plist),
            has_embedded_profile=has_profile,
            nested_bundles=nested,
        )


def print_ipa_info(info: IpaInfo) -> None:
    """打印 IPA 关键信息。"""
    print("IPA Info:")
    print(f"  Input               : {info.input_ipa}")
    print(f"  Main App            : {info.main_app.name}")
    print(f"  Main Bundle ID      : {info.main_app.bundle_id or '-'}")
    print(f"  Display Name        : {info.display_name or '-'}")
    print(f"  Version             : {info.version or '-'}")
    print(f"  Build               : {info.build or '-'}")
    print(f"  Minimum OS Version  : {info.min_os_version or '-'}")
    print(f"  Embedded Profile    : {'yes' if info.has_embedded_profile else 'no'}")
    if info.url_schemes:
        print(f"  URL Schemes         : {', '.join(info.url_schemes)}")
    else:
        print("  URL Schemes         : -")

    print(f"  Nested Bundles      : {len(info.nested_bundles)}")
    for b in info.nested_bundles:
        print(f"    - {b.path} | {b.bundle_id or '-'} | {b.package_type or '-'}")
