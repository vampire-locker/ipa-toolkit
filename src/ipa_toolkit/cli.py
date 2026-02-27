"""
`ipa-toolkit` 的命令行入口模块。

负责收集重签名参数与 `Info.plist` 操作参数，并调用 `ipa_toolkit.ipa.resign_ipa`。
"""

import argparse
import os
import sys
from collections.abc import Sequence

from .inspect import inspect_ipa, print_ipa_info
from .ipa import resign_ipa
from .provisioning import load_mobileprovision, resolve_sign_identity_from_profile
from .types import Op


def _add_op(ops: list[Op], scope: str, kind: str, spec: str) -> None:
    """将一条命令行参数规范转换为内部 `Op` 并追加到列表。"""
    if kind in ("delete",):
        if not spec:
            raise SystemExit(f"Error: missing KEY_PATH for {kind}")
        ops.append(Op(scope=scope, kind=kind, key_path=spec, value=None))
        return

    if "=" not in spec:
        raise SystemExit(f"Error: expected KEY_PATH=VALUE, got: {spec}")
    k, v = spec.split("=", 1)
    if not k:
        raise SystemExit(f"Error: empty KEY_PATH in: {spec}")
    ops.append(Op(scope=scope, kind=kind, key_path=k, value=v))


def _add_set_variants(parser: argparse.ArgumentParser, name: str, help_text: str) -> None:
    """注册支持 all/main/ext 作用域的“设置类”参数。"""
    parser.add_argument(name, action="append", default=[], metavar="KEY_PATH=VALUE", help=help_text)
    parser.add_argument(f"{name}-main", action="append", default=[], metavar="KEY_PATH=VALUE",
                        help=f"{help_text} (only main app)")
    parser.add_argument(f"{name}-ext", action="append", default=[], metavar="KEY_PATH=VALUE",
                        help=f"{help_text} (only extensions)")


def _add_delete_variants(parser: argparse.ArgumentParser, name: str, help_text: str) -> None:
    """注册支持 all/main/ext 作用域的“删除类”参数。"""
    parser.add_argument(name, action="append", default=[], metavar="KEY_PATH", help=help_text)
    parser.add_argument(f"{name}-main", action="append", default=[], metavar="KEY_PATH",
                        help=f"{help_text} (only main app)")
    parser.add_argument(f"{name}-ext", action="append", default=[], metavar="KEY_PATH",
                        help=f"{help_text} (only extensions)")


def _parse_ops(ns: argparse.Namespace) -> list[Op]:
    """把 argparse 命名空间整理成统一的 `Op` 序列。"""
    ops: list[Op] = []

    # 操作作用域支持：
    # - all：主应用与扩展全部生效
    # - main：仅主应用生效
    # - ext：仅扩展/服务生效
    for spec in ns.set:
        _add_op(ops, "all", "set_string", spec)
    for spec in ns.set_main:
        _add_op(ops, "main", "set_string", spec)
    for spec in ns.set_ext:
        _add_op(ops, "ext", "set_string", spec)

    for spec in ns.set_int:
        _add_op(ops, "all", "set_int", spec)
    for spec in ns.set_int_main:
        _add_op(ops, "main", "set_int", spec)
    for spec in ns.set_int_ext:
        _add_op(ops, "ext", "set_int", spec)

    for spec in ns.set_bool:
        _add_op(ops, "all", "set_bool", spec)
    for spec in ns.set_bool_main:
        _add_op(ops, "main", "set_bool", spec)
    for spec in ns.set_bool_ext:
        _add_op(ops, "ext", "set_bool", spec)

    for spec in ns.delete:
        _add_op(ops, "all", "delete", spec)
    for spec in ns.delete_main:
        _add_op(ops, "main", "delete", spec)
    for spec in ns.delete_ext:
        _add_op(ops, "ext", "delete", spec)

    for spec in ns.array_add:
        _add_op(ops, "all", "array_add", spec)
    for spec in ns.array_add_main:
        _add_op(ops, "main", "array_add", spec)
    for spec in ns.array_add_ext:
        _add_op(ops, "ext", "array_add", spec)

    for spec in ns.array_remove:
        _add_op(ops, "all", "array_remove", spec)
    for spec in ns.array_remove_main:
        _add_op(ops, "main", "array_remove", spec)
    for spec in ns.array_remove_ext:
        _add_op(ops, "ext", "array_remove", spec)

    return ops


def _log_step(message: str) -> None:
    """输出简洁的流程阶段提示。"""
    print(f"[ipa-toolkit] {message}")


def _choose_candidate(
    *,
    kind: str,
    candidates: list[str],
    required_flag: str,
    context: str,
) -> str:
    """当候选有多个时，交互式让用户选择；非交互环境则报错。"""
    ordered = sorted(os.path.abspath(x) for x in candidates)
    if not sys.stdin.isatty():
        names = ", ".join(os.path.basename(x) for x in ordered)
        raise SystemExit(
            f"Error: multiple {kind} found {context} in non-interactive mode.\n"
            f"Candidates: {names}\n"
            f"Please pass the desired one via {required_flag}.\n"
        )

    print(f"Multiple {kind} found {context}. Please choose one:")
    for i, path in enumerate(ordered, start=1):
        print(f"  {i}) {path}")

    while True:
        raw = input(f"Select {kind} [1-{len(ordered)}]: ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(ordered):
                selected = ordered[idx - 1]
                print(f"Selected {kind}: {selected}")
                return selected
        print("Invalid selection. Please enter a valid number.")


def _find_profile_near_input(input_ipa: str) -> str:
    """在输入 IPA 同级目录自动发现 profile。"""
    parent = os.path.dirname(input_ipa)
    stem = os.path.splitext(os.path.basename(input_ipa))[0]

    candidates: list[str] = []
    preferred = os.path.join(parent, f"{stem}.mobileprovision")
    if os.path.isfile(preferred):
        return preferred

    with os.scandir(parent) as it:
        for entry in it:
            if not entry.is_file():
                continue
            if entry.name.lower().endswith(".mobileprovision"):
                candidates.append(entry.path)

    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        return _choose_candidate(
            kind="provisioning profiles",
            candidates=candidates,
            required_flag="-p/--profile",
            context=f"next to input ipa ({os.path.basename(input_ipa)})",
        )
    return ""


def _find_input_ipa_in_cwd() -> str:
    """在当前工作目录自动发现输入 IPA。"""
    cwd = os.getcwd()
    candidates: list[str] = []
    with os.scandir(cwd) as it:
        for entry in it:
            if not entry.is_file():
                continue
            if entry.name.lower().endswith(".ipa"):
                candidates.append(entry.path)

    if len(candidates) == 1:
        return os.path.abspath(candidates[0])
    if len(candidates) > 1:
        return _choose_candidate(
            kind=".ipa files",
            candidates=candidates,
            required_flag="-i/--input",
            context="in current directory",
        )
    raise SystemExit(
        "Error: missing -i/--input and no .ipa file found in current directory.\n"
        "Hint: pass input ipa path via -i.\n"
    )


def build_parser() -> argparse.ArgumentParser:
    """构建并返回 `ipa-toolkit` 命令行参数解析器。"""
    p = argparse.ArgumentParser(
        prog="ipa-toolkit",
        formatter_class=argparse.RawTextHelpFormatter,
        description=(
            "Modify ipa (bundle id / version / display name / Info.plist keys) and re-sign.\n"
            "It preserves ALL top-level items in the ipa "
            "(Payload, Symbols, SwiftSupport, etc.) when re-zipping."
        ),
    )

    p.add_argument("-i", "--input", default="", help="Input .ipa path")
    p.add_argument(
        "-o",
        "--output",
        default="",
        help="Output .ipa path (default: <input>.resigned.ipa)",
    )
    # 此处不设为 argparse 的 required，便于输出更可操作的缺参提示。
    p.add_argument(
        "-s",
        "--sign-identity",
        default="",
        help="Codesign identity name (list with: security find-identity -v -p codesigning)",
    )
    p.add_argument(
        "-p",
        "--profile",
        default="",
        help="Provisioning profile (.mobileprovision) to embed into main app",
    )
    p.add_argument(
        "-e",
        "--entitlements",
        default="",
        help="Entitlements plist to use for signing (optional)",
    )
    p.add_argument(
        "--main-app-name",
        default="",
        help="Main app bundle name under Payload (e.g. MyApp.app) when multiple .app exist",
    )
    p.add_argument(
        "--strict-entitlements",
        action="store_true",
        help="Fail when required entitlements identifiers are missing",
    )
    p.add_argument(
        "--inspect",
        action="store_true",
        help="Only inspect and print ipa key info without re-signing or modifying",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview re-sign changes without modifying files or creating output ipa",
    )
    p.add_argument(
        "--auto-rewrite-bundle-id-values",
        action="store_true",
        help="Auto rewrite bundle-id-like string values in Info.plist when using -b",
    )
    p.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary working directory (prints its path at the end)",
    )
    p.add_argument("--verbose", action="store_true", help="Verbose logging")

    p.add_argument(
        "-b",
        "--bundle-id",
        default="",
        help="New main app CFBundleIdentifier (prefix replace for extensions)",
    )
    p.add_argument("-v", "--version", default="", help="New CFBundleShortVersionString")
    p.add_argument("-n", "--build", default="", help="New CFBundleVersion")
    p.add_argument(
        "-d",
        "--display-name",
        default="",
        help="New CFBundleDisplayName (also sets CFBundleName)",
    )

    _add_set_variants(p, "--set", "Set Info.plist value as string")
    _add_set_variants(p, "--set-int", "Set Info.plist value as integer")
    _add_set_variants(p, "--set-bool", "Set Info.plist value as bool (true/false/1/0)")
    _add_delete_variants(p, "--delete", "Delete Info.plist key/path")
    _add_set_variants(p, "--array-add", "Append a string element to an array at KEY_PATH")
    _add_set_variants(
        p,
        "--array-remove",
        "Remove string elements matching VALUE from array at KEY_PATH",
    )

    return p


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 入口：解析参数、校验输入并调用重签名主流程。"""
    parser = build_parser()
    ns = parser.parse_args(argv)
    if ns.inspect and ns.dry_run:
        raise SystemExit("Error: --inspect and --dry-run cannot be used together.")

    ops = _parse_ops(ns)

    def _abs(p: str) -> str:
        """将输入路径展开为绝对路径，统一后续文件校验逻辑。"""
        return os.path.abspath(os.path.expanduser(p))

    _log_step("Resolving input ipa")
    if ns.input:
        input_ipa = _abs(ns.input)
        if not os.path.isfile(input_ipa):
            raise SystemExit(f"Error: ipa not found: {input_ipa}")
        _log_step(f"Using input ipa: {input_ipa}")
    else:
        input_ipa = _find_input_ipa_in_cwd()
        _log_step(f"Auto input ipa: {input_ipa}")

    if ns.inspect:
        _log_step("Inspecting ipa metadata")
        info = inspect_ipa(input_ipa, main_app_name=ns.main_app_name or "")
        print_ipa_info(info)
        return 0

    _log_step("Resolving output ipa")
    output_ipa = _abs(ns.output) if ns.output else ""
    if not output_ipa:
        base = os.path.basename(input_ipa)
        stem = base[:-4] if base.lower().endswith(".ipa") else base
        output_ipa = os.path.join(os.path.dirname(input_ipa), f"{stem}.resigned.ipa")
    _log_step(f"Output ipa: {output_ipa}")

    _log_step("Resolving provisioning profile")
    profile = _abs(ns.profile) if ns.profile else _find_profile_near_input(input_ipa)
    if profile:
        src = "provided" if ns.profile else "auto"
        _log_step(f"Using {src} profile: {profile}")
    else:
        _log_step("No profile selected")

    entitlements = _abs(ns.entitlements) if ns.entitlements else ""
    sign_identity = (ns.sign_identity or "").strip()

    _log_step("Resolving sign identity")
    if not sign_identity:
        if not profile:
            raise SystemExit(
                "Error: missing -s/--sign-identity.\n"
                "Hint: pass -s explicitly, or provide/auto-detect -p profile "
                "so identity can be inferred.\n"
            )
        try:
            sign_identity = resolve_sign_identity_from_profile(load_mobileprovision(profile))
        except RuntimeError as e:
            raise SystemExit(
                "Error: failed to infer sign identity from provisioning profile.\n"
                f"Detail: {e}\n"
                "Hint: pass -s explicitly.\n"
            ) from e
        _log_step(f"Auto sign identity: {sign_identity}")
    else:
        _log_step(f"Using provided sign identity: {sign_identity}")

    if ns.dry_run:
        _log_step("Dry-run mode enabled (no file modifications)")
    _log_step("Starting re-sign pipeline")
    resign_ipa(
        input_ipa=input_ipa,
        output_ipa=output_ipa,
        sign_identity=sign_identity,
        profile_path=profile,
        entitlements_path=entitlements,
        main_app_name=ns.main_app_name or "",
        strict_entitlements=bool(ns.strict_entitlements),
        keep_temp=bool(ns.keep_temp),
        verbose=bool(ns.verbose),
        new_bundle_id=ns.bundle_id or "",
        new_version=ns.version or "",
        new_build=ns.build or "",
        new_display_name=ns.display_name or "",
        ops=ops,
        auto_rewrite_bundle_id_values=bool(ns.auto_rewrite_bundle_id_values),
        dry_run=bool(ns.dry_run),
    )
    return 0
