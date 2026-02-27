"""
将高层 `Op` 操作规范应用到 plist 字典对象。
"""

from __future__ import annotations

from collections.abc import Sequence

from .plist_edit import array_add_string, array_remove_string, delete_value, set_value
from .types import Op


def _bool_from_str(s: str) -> bool:
    """将常见布尔字符串（true/false/1/0 等）转换为 bool。"""
    v = s.strip().lower()
    if v in ("true", "1", "yes", "y"):
        return True
    if v in ("false", "0", "no", "n"):
        return False
    raise ValueError(f"invalid bool: {s}")


def apply_ops(plist_obj: dict, ops: Sequence[Op]) -> None:
    """按顺序将 `Op` 列表应用到给定 plist 字典。"""
    for op in ops:
        try:
            if op.kind == "set_string":
                set_value(plist_obj, op.key_path, op.value or "")
            elif op.kind == "set_int":
                raw = op.value or "0"
                set_value(plist_obj, op.key_path, int(raw))
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
        except (TypeError, ValueError) as e:
            suffix = f"={op.value}" if op.value is not None else ""
            raise SystemExit(
                f"Error: invalid plist operation {op.kind} on {op.key_path}{suffix}: {e}"
            ) from e


def _rewrite_bundle_id_in_string(value: str, *, old_id: str, new_id: str) -> str:
    """重写单个字符串中的 bundle id（仅精确值与前缀子标识）。"""
    if value == new_id or value.startswith(new_id + "."):
        return value
    if value == old_id:
        return new_id
    if value.startswith(old_id + "."):
        return new_id + value[len(old_id):]
    return value


def rewrite_bundle_id_strings(obj: object, *, old_id: str, new_id: str) -> int:
    """递归重写 plist 结构中的 bundle id 字符串，返回替换次数。"""
    if not old_id or old_id == new_id:
        return 0

    count = 0

    def _walk(node: object) -> None:
        nonlocal count
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if isinstance(value, str):
                    replaced = _rewrite_bundle_id_in_string(value, old_id=old_id, new_id=new_id)
                    if replaced != value:
                        node[key] = replaced
                        count += 1
                elif isinstance(value, (dict, list)):
                    _walk(value)
        elif isinstance(node, list):
            for i, value in enumerate(node):
                if isinstance(value, str):
                    replaced = _rewrite_bundle_id_in_string(value, old_id=old_id, new_id=new_id)
                    if replaced != value:
                        node[i] = replaced
                        count += 1
                elif isinstance(value, (dict, list)):
                    _walk(value)

    _walk(obj)
    return count


def rewrite_bundle_id_in_url_types(plist_obj: dict, *, old_id: str, new_id: str) -> int:
    """重写 `CFBundleURLTypes` 里的 bundle id 相关值，返回替换次数。"""
    if not old_id or old_id == new_id:
        return 0

    url_types = plist_obj.get("CFBundleURLTypes")
    if not isinstance(url_types, list):
        return 0

    count = 0
    for item in url_types:
        if not isinstance(item, dict):
            continue

        name = item.get("CFBundleURLName")
        if isinstance(name, str):
            replaced = _rewrite_bundle_id_in_string(name, old_id=old_id, new_id=new_id)
            if replaced != name:
                item["CFBundleURLName"] = replaced
                count += 1

        schemes = item.get("CFBundleURLSchemes")
        if not isinstance(schemes, list):
            continue
        for i, scheme in enumerate(schemes):
            if not isinstance(scheme, str):
                continue
            replaced = _rewrite_bundle_id_in_string(scheme, old_id=old_id, new_id=new_id)
            if replaced != scheme:
                schemes[i] = replaced
                count += 1

    return count
