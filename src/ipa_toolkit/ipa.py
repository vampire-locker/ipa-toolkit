"""
IPA 重签名主流程模块。

整体步骤如下：
1) 将 IPA 解压到临时目录。
2) 在 `Payload/*.app` 下定位主应用，并收集其嵌套应用包（`.appex`、`.xpc`、嵌套 `.app`）。
3) 应用 `Info.plist` 修改（包名、版本号、构建号、显示名及自定义操作）。
4) 按需向主应用注入 `mobileprovision`。
5) 为每个应用包生成或提取签名权限（`entitlements`）。
6) 递归完成 Framework/动态库/扩展签名，再签应用包本体。
7) 保留顶层目录结构并重新打包输出。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Sequence

from . import codesign
from .bundle_scan import bundle_new_id_for, find_bundles_under, find_main_app
from .entitlements import build_entitlements_by_bundle
from .pipeline_utils import run_cmd, sign_bundle_recursive
from .plist_edit import (
    load_plist,
    save_plist_binary,
)
from .plist_ops import (
    apply_ops,
    rewrite_bundle_id_in_url_types,
    rewrite_bundle_id_strings,
)
from .provisioning import ProvisioningProfile, load_mobileprovision
from .types import Op


def resign_ipa(
    *,
    input_ipa: str,
    output_ipa: str,
    sign_identity: str,
    profile_path: str,
    entitlements_path: str,
    main_app_name: str,
    strict_entitlements: bool,
    keep_temp: bool,
    verbose: bool,
    new_bundle_id: str,
    new_version: str,
    new_build: str,
    new_display_name: str,
    ops: Sequence[Op],
    auto_rewrite_bundle_id_values: bool = False,
    dry_run: bool = False,
) -> None:
    """对外入口：校验输入并在临时目录内执行完整重签名流程。"""
    # 供 CLI 调用的公开入口，具体执行逻辑在 `_resign_ipa_in_tempdir`。
    if profile_path and not os.path.isfile(profile_path):
        raise SystemExit(f"Error: profile not found: {profile_path}")
    if entitlements_path and not os.path.isfile(entitlements_path):
        raise SystemExit(f"Error: entitlements not found: {entitlements_path}")

    profile: ProvisioningProfile | None = None
    if profile_path:
        profile = load_mobileprovision(profile_path)

    td = tempfile.mkdtemp(prefix="resign_ipa_") if keep_temp else ""
    try:
        if not td:
            with tempfile.TemporaryDirectory(prefix="resign_ipa_") as _td:
                td = _td
                _resign_ipa_in_tempdir(
                    td,
                    input_ipa=input_ipa,
                    output_ipa=output_ipa,
                    sign_identity=sign_identity,
                    profile=profile,
                    profile_path=profile_path,
                    entitlements_path=entitlements_path,
                    main_app_name=main_app_name,
                    strict_entitlements=strict_entitlements,
                    keep_temp=keep_temp,
                    verbose=verbose,
                    new_bundle_id=new_bundle_id,
                    new_version=new_version,
                    new_build=new_build,
                    new_display_name=new_display_name,
                    ops=ops,
                    auto_rewrite_bundle_id_values=auto_rewrite_bundle_id_values,
                    dry_run=dry_run,
                )
                return

        _resign_ipa_in_tempdir(
            td,
            input_ipa=input_ipa,
            output_ipa=output_ipa,
            sign_identity=sign_identity,
            profile=profile,
            profile_path=profile_path,
            entitlements_path=entitlements_path,
            main_app_name=main_app_name,
            strict_entitlements=strict_entitlements,
            keep_temp=keep_temp,
            verbose=verbose,
            new_bundle_id=new_bundle_id,
            new_version=new_version,
            new_build=new_build,
            new_display_name=new_display_name,
            ops=ops,
            auto_rewrite_bundle_id_values=auto_rewrite_bundle_id_values,
            dry_run=dry_run,
        )
    except Exception:
        if keep_temp and td:
            print(f"Temp dir kept: {td}")
        raise
    finally:
        if not keep_temp and td:
            shutil.rmtree(td, ignore_errors=True)


def _resign_ipa_in_tempdir(
    td: str,
    *,
    input_ipa: str,
    output_ipa: str,
    sign_identity: str,
    profile: ProvisioningProfile | None,
    profile_path: str,
    entitlements_path: str,
    main_app_name: str,
    strict_entitlements: bool,
    keep_temp: bool,
    verbose: bool,
    new_bundle_id: str,
    new_version: str,
    new_build: str,
    new_display_name: str,
    ops: Sequence[Op],
    auto_rewrite_bundle_id_values: bool,
    dry_run: bool,
) -> None:
    """在已准备好的临时目录中执行解包、修改、签名与回包。"""
    # 先解压到 `<temp>/unzipped`，后续可完整回包所有顶层目录。
    root = os.path.join(td, "unzipped")
    os.makedirs(root, exist_ok=True)
    run_cmd(["/usr/bin/unzip", "-q", input_ipa, "-d", root], verbose=verbose)

    macosx = os.path.join(root, "__MACOSX")
    if os.path.isdir(macosx):
        shutil.rmtree(macosx, ignore_errors=True)

    payload = os.path.join(root, "Payload")
    if not os.path.isdir(payload):
        raise SystemExit("Error: Payload not found in ipa.")

    app_path = find_main_app(payload, main_app_name)
    if not app_path:
        raise SystemExit("Error: .app not found under Payload/.")
    if verbose:
        print(f"App: {app_path}")

    main_info = os.path.join(app_path, "Info.plist")
    main_plist = load_plist(main_info)
    if not isinstance(main_plist, dict):
        raise SystemExit("Error: main Info.plist is not a dict")

    old_main_id = main_plist.get("CFBundleIdentifier", "")
    if not isinstance(old_main_id, str) or not old_main_id:
        raise SystemExit("Error: failed to read CFBundleIdentifier from main Info.plist")

    bundles = find_bundles_under(app_path)
    if verbose:
        print(f"Bundles: {len(bundles)}")

    # 记录应用包路径到 `(old_id, new_id)` 的映射关系。
    bundle_ids: dict[str, tuple[str, str]] = {}
    changed_bundle_ids = 0
    changed_url_types = 0
    changed_general_bundle_strings = 0

    # 对每个应用包执行 Info.plist 修改。
    ops_all = [o for o in ops if o.scope == "all"]
    ops_main = [o for o in ops if o.scope == "main"]
    ops_ext = [o for o in ops if o.scope == "ext"]

    for b in bundles:
        info_path = os.path.join(b, "Info.plist")
        if not os.path.isfile(info_path):
            continue
        plist_obj = load_plist(info_path)
        if not isinstance(plist_obj, dict):
            continue

        old_id = plist_obj.get("CFBundleIdentifier", "")
        if not isinstance(old_id, str) or not old_id:
            continue

        new_id = bundle_new_id_for(old_id, old_main_id, new_bundle_id)
        bundle_ids[b] = (old_id, new_id)

        if new_bundle_id and new_id != old_id:
            url_type_replaced = rewrite_bundle_id_in_url_types(
                plist_obj,
                old_id=old_id,
                new_id=new_id,
            )
            changed_url_types += url_type_replaced
            if verbose and url_type_replaced:
                print(f"Rewrote {url_type_replaced} URLTypes bundle-id value(s): {info_path}")

        if auto_rewrite_bundle_id_values and new_bundle_id and new_id != old_id:
            replaced_count = rewrite_bundle_id_strings(
                plist_obj,
                old_id=old_id,
                new_id=new_id,
            )
            changed_general_bundle_strings += replaced_count
            if verbose and replaced_count:
                print(f"Rewrote {replaced_count} bundle-id string(s): {info_path}")

        if new_bundle_id and new_id != old_id:
            changed_bundle_ids += 1
            plist_obj["CFBundleIdentifier"] = new_id
        if new_version:
            plist_obj["CFBundleShortVersionString"] = new_version
        if new_build:
            plist_obj["CFBundleVersion"] = new_build
        if new_display_name:
            plist_obj["CFBundleDisplayName"] = new_display_name
            plist_obj["CFBundleName"] = new_display_name

        apply_ops(plist_obj, ops_all)
        if b == app_path:
            apply_ops(plist_obj, ops_main)
        else:
            apply_ops(plist_obj, ops_ext)

        if not dry_run:
            save_plist_binary(info_path, plist_obj)

    # 向主应用注入描述文件。
    if profile_path and not dry_run:
        shutil.copyfile(profile_path, os.path.join(app_path, "embedded.mobileprovision"))

    # 为每个应用包准备签名权限。
    explicit_entitlements: dict | None = None
    if entitlements_path:
        ent_obj = load_plist(entitlements_path)
        if not isinstance(ent_obj, dict):
            raise SystemExit("Error: entitlements plist is not a dict")
        explicit_entitlements = ent_obj

    ent_by_bundle = build_entitlements_by_bundle(
        bundles=bundles,
        bundle_ids=bundle_ids,
        explicit_entitlements=explicit_entitlements,
        profile=profile,
        extract_entitlements=codesign.extract_entitlements,
        require_app_identifier=strict_entitlements,
    )

    if dry_run:
        print("Dry run:")
        print(f"  Input : {input_ipa}")
        print(f"  Output: {output_ipa}")
        print(f"  App   : {os.path.basename(app_path)}")
        print(f"  OldID : {old_main_id}")
        if new_bundle_id:
            print(f"  NewID : {new_bundle_id}")
        print(f"  Bundles scanned             : {len(bundles)}")
        print(f"  Bundle identifiers to change: {changed_bundle_ids}")
        print(f"  URLTypes entries to rewrite : {changed_url_types}")
        if auto_rewrite_bundle_id_values:
            print(f"  Extra string rewrites       : {changed_general_bundle_strings}")
        if profile_path:
            print(f"  Embed profile               : yes ({profile_path})")
        else:
            print("  Embed profile               : no")
        print(f"  Sign identity               : {sign_identity}")
        print(f"  Entitlements prepared       : {len(ent_by_bundle)} bundle(s)")
        if ops:
            print(f"  Custom plist ops            : {len(ops)}")
        print("  Note                        : no files were modified")
        return

    # 从主应用开始递归签名所有组件。
    sign_bundle_recursive(
        app_path,
        identity=sign_identity,
        entitlements_by_bundle=ent_by_bundle,
        verbose=verbose,
    )
    codesign.verify(app_path)

    # 回包所有顶层目录（如 Payload、Symbols 等）。
    # `-y` 表示保留符号链接本身而非解引用，对 Framework 场景很重要。
    items = [x for x in os.listdir(root) if x not in ("__MACOSX",) and x]
    if os.path.exists(output_ipa):
        os.remove(output_ipa)
    run_cmd(["/usr/bin/zip", "-qry", "-y", output_ipa, *items], cwd=root, verbose=verbose)

    print("Done:")
    print(f"  Input : {input_ipa}")
    print(f"  Output: {output_ipa}")
    print(f"  App   : {os.path.basename(app_path)}")
    print(f"  OldID : {old_main_id}")
    if new_bundle_id:
        print(f"  NewID : {new_bundle_id}")
    if new_version:
        print(f"  Ver   : {new_version}")
    if new_build:
        print(f"  Build : {new_build}")
    if new_display_name:
        print(f"  Name  : {new_display_name}")
    if ops:
        print("  Plist : custom operations applied")
    if keep_temp:
        print(f"  Temp  : {td}")
