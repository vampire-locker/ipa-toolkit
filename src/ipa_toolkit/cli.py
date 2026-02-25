"""
`ipa-toolkit` 的命令行入口模块。

负责收集重签名参数与 `Info.plist` 操作参数，并调用 `ipa_toolkit.ipa.resign_ipa`。
"""

import argparse
import os
from collections.abc import Sequence

from .ipa import resign_ipa
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

    p.add_argument("-i", "--input", required=True, help="Input .ipa path")
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

    if not (ns.sign_identity or "").strip():
        raise SystemExit(
            "Error: missing -s/--sign-identity.\n"
            "Hint: list available codesigning identities with:\n"
            "  security find-identity -v -p codesigning\n"
            "Then pass one of the shown names via -s.\n"
        )

    ops = _parse_ops(ns)

    def _abs(p: str) -> str:
        """将输入路径展开为绝对路径，统一后续文件校验逻辑。"""
        return os.path.abspath(os.path.expanduser(p))

    input_ipa = _abs(ns.input)
    if not os.path.isfile(input_ipa):
        raise SystemExit(f"Error: ipa not found: {input_ipa}")

    output_ipa = _abs(ns.output) if ns.output else ""
    if not output_ipa:
        base = os.path.basename(input_ipa)
        stem = base[:-4] if base.lower().endswith(".ipa") else base
        output_ipa = os.path.join(os.path.dirname(input_ipa), f"{stem}.resigned.ipa")

    profile = _abs(ns.profile) if ns.profile else ""
    entitlements = _abs(ns.entitlements) if ns.entitlements else ""

    resign_ipa(
        input_ipa=input_ipa,
        output_ipa=output_ipa,
        sign_identity=ns.sign_identity,
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
    )
    return 0
