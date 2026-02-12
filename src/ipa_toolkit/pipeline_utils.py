from __future__ import annotations

"""
流程通用工具：命令执行与递归签名顺序控制。
"""

import os
import subprocess

from . import codesign


def run_cmd(cmd: list[str], *, cwd: str | None = None, verbose: bool = False) -> None:
    """执行外部命令，失败时抛出带 stderr 的异常。"""
    if verbose:
        if cwd:
            print(f"+ (cd {cwd}) {' '.join(cmd)}")
        else:
            print(f"+ {' '.join(cmd)}")
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr.decode(errors='replace')}")


def sign_bundle_recursive(
    bundle_path: str,
    *,
    identity: str,
    entitlements_by_bundle: dict[str, dict | None],
    verbose: bool = False,
) -> None:
    """按依赖顺序递归签名应用包及其嵌套组件。"""
    plugins = os.path.join(bundle_path, "PlugIns")
    if os.path.isdir(plugins):
        for name in os.listdir(plugins):
            p = os.path.join(plugins, name)
            if os.path.isdir(p) and name.endswith(".appex"):
                sign_bundle_recursive(
                    p,
                    identity=identity,
                    entitlements_by_bundle=entitlements_by_bundle,
                    verbose=verbose,
                )

    watch = os.path.join(bundle_path, "Watch")
    if os.path.isdir(watch):
        for root, dirs, _files in os.walk(watch):
            for d in dirs:
                if d.endswith(".app"):
                    sign_bundle_recursive(
                        os.path.join(root, d),
                        identity=identity,
                        entitlements_by_bundle=entitlements_by_bundle,
                        verbose=verbose,
                    )

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

    xpcs = os.path.join(bundle_path, "XPCServices")
    if os.path.isdir(xpcs):
        for name in os.listdir(xpcs):
            p = os.path.join(xpcs, name)
            if os.path.isdir(p) and name.endswith(".xpc"):
                sign_bundle_recursive(
                    p,
                    identity=identity,
                    entitlements_by_bundle=entitlements_by_bundle,
                    verbose=verbose,
                )

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
