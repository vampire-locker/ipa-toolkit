from __future__ import annotations

"""
IPA (re)signing pipeline.

High-level flow:
1) Unzip IPA into a temporary directory.
2) Find the main app bundle under `Payload/*.app` and all nested bundles under it
   (`.appex`, `.xpc`, nested `.app`).
3) Apply Info.plist edits (bundle id / version / build / display name + generic
   operations).
4) Embed provisioning profile into the main app (optional).
5) Determine entitlements per bundle:
   - explicit entitlements plist if provided
   - else try to extract from the existing signature
   - else fall back to entitlements from the provided provisioning profile
6) Recursively codesign frameworks/dylibs/extensions/xpc, then the bundles.
7) Zip everything back, preserving all top-level items.
"""

import os
import shutil
import tempfile
from typing import Sequence

from . import codesign
from .bundle_scan import bundle_new_id_for, find_bundles_under, find_main_app
from .entitlements import build_entitlements_by_bundle
from .pipeline_utils import run_cmd, sign_bundle_recursive
from .plist_edit import (
    load_plist,
    save_plist_binary,
)
from .plist_ops import apply_ops
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
    keep_temp: bool,
    verbose: bool,
    new_bundle_id: str,
    new_version: str,
    new_build: str,
    new_display_name: str,
    ops: Sequence[Op],
) -> None:
    # Public API used by the CLI. The actual work happens in `_resign_ipa_in_tempdir`.
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
                    keep_temp=keep_temp,
                    verbose=verbose,
                    new_bundle_id=new_bundle_id,
                    new_version=new_version,
                    new_build=new_build,
                    new_display_name=new_display_name,
                    ops=ops,
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
            keep_temp=keep_temp,
            verbose=verbose,
            new_bundle_id=new_bundle_id,
            new_version=new_version,
            new_build=new_build,
            new_display_name=new_display_name,
            ops=ops,
        )
    except Exception:
        if keep_temp and td:
            print(f"Temp dir kept: {td}")
        raise
    finally:
        if keep_temp:
            return
        if td:
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
    keep_temp: bool,
    verbose: bool,
    new_bundle_id: str,
    new_version: str,
    new_build: str,
    new_display_name: str,
    ops: Sequence[Op],
) -> None:
    # Unzip to `<temp>/unzipped` so we can zip back all top-level items later.
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

    # Map bundle_path -> (old_id, new_id)
    bundle_ids: dict[str, tuple[str, str]] = {}

    # Apply Info.plist changes for each bundle.
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

        save_plist_binary(info_path, plist_obj)

    # Embed profile into main app.
    if profile_path:
        shutil.copyfile(profile_path, os.path.join(app_path, "embedded.mobileprovision"))

    # Prepare entitlements per bundle.
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
    )

    # Sign everything starting from main app bundle.
    sign_bundle_recursive(
        app_path,
        identity=sign_identity,
        entitlements_by_bundle=ent_by_bundle,
        verbose=verbose,
    )
    codesign.verify(app_path)

    # Zip back all top-level items (Payload, Symbols, etc.)
    # -y: store symbolic links as links (do NOT follow); important for many Framework bundles.
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
