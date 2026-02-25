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
