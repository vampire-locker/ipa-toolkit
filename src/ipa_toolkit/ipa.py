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
import subprocess
import tempfile
from typing import Sequence

from . import codesign
from .types import Op
from .plist_edit import (
    array_add_string,
    array_remove_string,
    delete_value,
    load_plist,
    save_plist_binary,
    set_value,
)
from .provisioning import ProvisioningProfile, load_mobileprovision


def _run(cmd: list[str], *, cwd: str | None = None, verbose: bool = False) -> None:
    if verbose:
        if cwd:
            print(f"+ (cd {cwd}) {' '.join(cmd)}")
        else:
            print(f"+ {' '.join(cmd)}")
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr.decode(errors='replace')}")


def _find_first_dir(parent: str, suffix: str) -> str:
    for name in os.listdir(parent):
        p = os.path.join(parent, name)
        if os.path.isdir(p) and name.endswith(suffix):
            return p
    return ""


def _find_bundles_under(app_path: str) -> list[str]:
    # Walk the app bundle and collect everything that looks like a signable bundle.
    out: list[str] = []
    for root, dirs, _files in os.walk(app_path):
        for d in dirs:
            if d.endswith(".app") or d.endswith(".appex") or d.endswith(".xpc"):
                out.append(os.path.join(root, d))
        # We still want to descend because .appex might contain .app etc.
    # Ensure main app first for id mapping convenience.
    out.sort(key=lambda p: (0 if p == app_path else 1, len(p)))
    return out


def _bundle_new_id_for(old_id: str, old_main_id: str, new_main_id: str) -> str:
    # Keep the old identifier unless it's the main bundle id or shares its prefix.
    if not new_main_id:
        return old_id
    if old_id == old_main_id:
        return new_main_id
    if old_id.startswith(old_main_id + "."):
        return new_main_id + old_id[len(old_main_id):]
    return old_id


def _bool_from_str(s: str) -> bool:
    v = s.strip().lower()
    if v in ("true", "1", "yes", "y"):
        return True
    if v in ("false", "0", "no", "n"):
        return False
    raise ValueError(f"invalid bool: {s}")


def _apply_ops(plist_obj: dict, ops: Sequence[Op]) -> None:
    for op in ops:
        if op.kind == "set_string":
            set_value(plist_obj, op.key_path, op.value or "")
        elif op.kind == "set_int":
            set_value(plist_obj, op.key_path, int(op.value or "0"))
        elif op.kind == "set_bool":
            set_value(plist_obj, op.key_path, _bool_from_str(op.value or "false"))
        elif op.kind == "delete":
            delete_value(plist_obj, op.key_path)
        elif op.kind == "array_add":
            array_add_string(plist_obj, op.key_path, op.value or "")
        elif op.kind == "array_remove":
            array_remove_string(plist_obj, op.key_path, op.value or "")
        else:
            raise RuntimeError(f"Unknown op: {op.kind}")


def _adjust_entitlements_for_bundle(
    ent: dict,
    *,
    team_id: str,
    old_bundle_id: str,
    new_bundle_id: str,
) -> dict:
    # When changing bundle id, some entitlements must match the new application
    # identifier prefix: "<TEAMID>.<BUNDLEID>".
    if not team_id or old_bundle_id == new_bundle_id:
        return ent

    out = dict(ent)
    new_prefix = f"{team_id}.{new_bundle_id}"

    for key in ("application-identifier", "com.apple.application-identifier"):
        if key in out:
            out[key] = new_prefix

    kag = out.get("keychain-access-groups")
    if isinstance(kag, list):
        old_prefix = f"{team_id}.{old_bundle_id}"
        new_kag = []
        for item in kag:
            if isinstance(item, str) and item.startswith(old_prefix):
                new_kag.append(new_prefix + item[len(old_prefix):])
            else:
                new_kag.append(item)
        out["keychain-access-groups"] = new_kag

    return out


def _sign_bundle_recursive(
    bundle_path: str,
    *,
    identity: str,
    entitlements_by_bundle: dict[str, dict | None],
    verbose: bool = False,
) -> None:
    # Sign order matters:
    # - sign nested bundles first (.appex, watch apps, xpc services)
    # - sign embedded frameworks/dylibs
    # - finally sign the bundle itself
    # 1) PlugIns
    plugins = os.path.join(bundle_path, "PlugIns")
    if os.path.isdir(plugins):
        for name in os.listdir(plugins):
            p = os.path.join(plugins, name)
            if os.path.isdir(p) and name.endswith(".appex"):
                _sign_bundle_recursive(
                    p,
                    identity=identity,
                    entitlements_by_bundle=entitlements_by_bundle,
                    verbose=verbose,
                )

    # 2) Watch apps
    watch = os.path.join(bundle_path, "Watch")
    if os.path.isdir(watch):
        # typical layout: Watch/*.app
        for root, dirs, _files in os.walk(watch):
            for d in dirs:
                if d.endswith(".app"):
                    _sign_bundle_recursive(
                        os.path.join(root, d),
                        identity=identity,
                        entitlements_by_bundle=entitlements_by_bundle,
                        verbose=verbose,
                    )

    # 3) Frameworks & dylibs
    frameworks = os.path.join(bundle_path, "Frameworks")
    if os.path.isdir(frameworks):
        for name in os.listdir(frameworks):
            p = os.path.join(frameworks, name)
            if os.path.isdir(p) and name.endswith(".framework"):
                codesign.remove_signature(p)
                codesign.sign(p, identity)
        for name in os.listdir(frameworks):
            p = os.path.join(frameworks, name)
            if os.path.isfile(p) and (name.endswith(".dylib") or name.endswith(".so")):
                codesign.remove_signature(p)
                codesign.sign(p, identity)

    # 4) XPC services
    xpcs = os.path.join(bundle_path, "XPCServices")
    if os.path.isdir(xpcs):
        for name in os.listdir(xpcs):
            p = os.path.join(xpcs, name)
            if os.path.isdir(p) and name.endswith(".xpc"):
                _sign_bundle_recursive(
                    p,
                    identity=identity,
                    entitlements_by_bundle=entitlements_by_bundle,
                    verbose=verbose,
                )

    # 5) Sign the bundle itself
    codesign.remove_signature(bundle_path)
    ents = entitlements_by_bundle.get(bundle_path)
    ent_path: str | None = None
    try:
        if ents is not None:
            ent_path = codesign.write_entitlements(ents)
        if verbose:
            suffix = " (no entitlements)" if ents is None else ""
            print(f"Signing: {bundle_path}{suffix}")
        codesign.sign(bundle_path, identity, entitlements_path=ent_path)
    finally:
        if ent_path and os.path.exists(ent_path):
            try:
                os.remove(ent_path)
            except OSError:
                pass


def resign_ipa(
    *,
    input_ipa: str,
    output_ipa: str,
    sign_identity: str,
    profile_path: str,
    entitlements_path: str,
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
    _run(["/usr/bin/unzip", "-q", input_ipa, "-d", root], verbose=verbose)

    macosx = os.path.join(root, "__MACOSX")
    if os.path.isdir(macosx):
        shutil.rmtree(macosx, ignore_errors=True)

    payload = os.path.join(root, "Payload")
    if not os.path.isdir(payload):
        raise SystemExit("Error: Payload not found in ipa.")

    app_path = _find_first_dir(payload, ".app")
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

    bundles = _find_bundles_under(app_path)
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

        new_id = _bundle_new_id_for(old_id, old_main_id, new_bundle_id)
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

        _apply_ops(plist_obj, ops_all)
        if b == app_path:
            _apply_ops(plist_obj, ops_main)
        else:
            _apply_ops(plist_obj, ops_ext)

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

    ent_by_bundle: dict[str, dict | None] = {}
    for b in bundles:
        if explicit_entitlements is not None:
            ent_by_bundle[b] = explicit_entitlements
            continue

        # Prefer entitlements extracted from the original signature. If the IPA is
        # unsigned / stripped, fall back to profile-derived entitlements.
        ent = codesign.extract_entitlements(b)
        if ent is None and profile is not None:
            ent = dict(profile.entitlements)
        if ent is None:
            ent_by_bundle[b] = None
            continue

        if profile is not None and b in bundle_ids:
            old_id, new_id = bundle_ids[b]
            ent = _adjust_entitlements_for_bundle(
                ent,
                team_id=profile.team_id,
                old_bundle_id=old_id,
                new_bundle_id=new_id,
            )
        ent_by_bundle[b] = ent

    # Sign everything starting from main app bundle.
    _sign_bundle_recursive(
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
    _run(["/usr/bin/zip", "-qry", "-y", output_ipa, *items], cwd=root, verbose=verbose)

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
